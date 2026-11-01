# src/league/offseason/snake_draft.py
"""
Snake Draft Orchestrator

Pick order: reverse standings (worst record picks first).
Teams with no games played are placed at the end of round 1 order.

Snake format:
  Round 1:  team[0]  → team[N-1]   (worst to best)
  Round 2:  team[N-1] → team[0]    (best to worst)
  Round 3:  team[0]  → team[N-1]
  ...

Each team drafts the best available player by prospect_rating.

Post-draft:
  - Drafted player added to team_players
  - Status set to 'minors'
  - RosterAssigner re-run for each team against full roster
"""

import logging
import random
from dataclasses import dataclass

from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.pick_rights_repo import PickRightsRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.team.roster_assigner import RosterAssigner

log = logging.getLogger(__name__)

ROUNDS = 20


def write_draft_order(
    conn, draft_id: str, league_id: str, draft_year: int, ordered_team_ids: list[str]
) -> None:
    """
    Persist the draft order and default pick rights for a draft.
    ordered_team_ids should be in pick order (index 0 = picks first).
    Safe to call on a fresh draft — clears any existing order first. Pick
    rights already written (and maybe traded, see
    src/league/trades/draft_picks.py) are kept.
    """
    draft_repo = DraftRepository(conn)
    draft_repo.clear_draft(draft_id)
    for pos, tid in enumerate(ordered_team_ids, 1):
        draft_repo.insert_draft_order(draft_id, tid, pos)
    PickRightsRepository(conn).ensure(league_id, draft_year, ordered_team_ids, ROUNDS)
    conn.commit()


@dataclass
class DraftPick:
    round: int
    pick: int  # overall pick number
    team_id: str
    team_name: str
    player_id: str
    player_name: str
    age: int
    position: str
    prospect_rating: int


class SnakeDraft:
    def __init__(self, conn, league_id: str, rng: random.Random | None = None):
        self.conn = conn
        self.league_id = league_id
        self.rng = rng or random.Random()
        self.player_repo = PlayerRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)
        self.draft_repo = DraftRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.team_game_repo = TeamGameRepository(conn)
        # {(round, original team): owner}, for picks traded away
        self._owners: dict[tuple[int, str], str] = {}

    def _owner(self, round_num: int, team_id: str) -> str:
        """The team that makes this team's pick in a round."""
        return self._owners.get((round_num, team_id), team_id)

    def run_snake_draft_with_order(
        self,
        draft_order: list[dict],
        year: int,
        league_id: str | None = None,
    ) -> list[DraftPick]:
        """
        Execute the snake draft using a pre-built (and already persisted) draft order.

        Args:
            draft_order: Ordered list of team dicts from _build_draft_order or draft_order table
            year:        Draft year (whose pick rights are used)
            league_id:   League scoping
        """
        log.info("Draft order: %s teams", len(draft_order))

        # 1. Load draft pool
        pool = self._load_draft_pool()
        log.info("Draft pool: %s players available", len(pool))

        if not pool:
            log.warning("Empty draft pool, skipping draft")
            return []

        # 2. Pre-compute prospect ratings
        rated = self._rate_pool(pool)

        # 3. Run snake: each pick goes to its owner in draft_pick_rights
        self._owners = PickRightsRepository(self.conn).owners(
            league_id or self.league_id, year
        )
        picks = self._run_snake(draft_order, rated)
        self.conn.commit()
        log.info("Completed %s picks across %s rounds", len(picks), ROUNDS)

        # 4. Re-run RosterAssigner for each team
        self._reassign_rosters(draft_order)
        self.conn.commit()

        return picks

    # -----------------------------------------------------------------------
    # Draft order
    # -----------------------------------------------------------------------

    def _build_draft_order(self, season_id: str) -> list[dict]:
        # Get all teams in this season with city/mascot in one query
        all_team_rows = self.draft_repo.get_all_teams_city_mascot(season_id)

        # Get win% per team
        stat_rows = self.team_game_repo.get_wl_for_league(self.league_id, season_id)

        standings = {}
        for row in stat_rows:
            w = row["wins"] or 0
            l = row["losses"] or 0
            total = w + l
            standings[row["team_id"]] = w / total if total > 0 else 0.0

        teams_with_games = []
        teams_without_games = []

        for row in all_team_rows:
            team_id = row["team_id"]
            entry = {
                "team_id": team_id,
                "team_name": f"{row['city']} {row['mascot']}",
                "win_pct": standings.get(team_id, None),
            }
            if entry["win_pct"] is None:
                teams_without_games.append(entry)
            else:
                teams_with_games.append(entry)

        if teams_with_games == []:
            log.warning("There are no teams with games in season %s", season_id)

        teams_with_games.sort(key=lambda t: t["win_pct"])
        return teams_with_games + teams_without_games

    # -----------------------------------------------------------------------
    # Draft pool
    # -----------------------------------------------------------------------

    def _load_draft_pool(self) -> list[PlayerRecord]:
        """Load all prospect players not on any team."""
        rows = self.draft_repo.get_prospects(self.league_id)

        players = []
        for row in rows:
            player = self.player_repo.look_up(row["id"])
            if player:
                players.append(player)
        return players

    def _rate_pool(self, pool: list[PlayerRecord]) -> list[tuple[PlayerRecord, int]]:
        """
        Return pool sorted best-to-worst by prospect_rating.
        Returns list of (player, rating) tuples.
        """
        rated = [(p, PlayerEvaluator.prospect_rating(p.skills)) for p in pool]
        rated.sort(key=lambda x: x[1], reverse=True)
        return rated

    # -----------------------------------------------------------------------
    # Snake draft
    # -----------------------------------------------------------------------

    def _run_snake(
        self,
        draft_order: list[dict],
        rated: list[tuple[PlayerRecord, int]],
    ) -> list[DraftPick]:
        """Execute the snake draft, returning all picks."""
        picks = []
        overall_pick = 1

        # available pool as ordered list — pop from front (best first)
        available = list(rated)
        names = {t["team_id"]: t["team_name"] for t in draft_order}

        for round_num in range(1, ROUNDS + 1):
            # Odd rounds: worst→best, even rounds: best→worst (snake)
            if round_num % 2 == 1:
                order = draft_order
            else:
                order = list(reversed(draft_order))

            for team_entry in order:
                if not available:
                    log.info("Draft pool exhausted at pick %s", overall_pick)
                    return picks

                player, rating = available.pop(0)
                team_id = self._owner(round_num, team_entry["team_id"])
                team_name = names.get(team_id, "")

                # Add to team_players
                self.team_repo.add_player(team_id, player.id)
                # Set status to minors
                self.status_repo.set_status(player.id, "minors")

                picks.append(
                    DraftPick(
                        round=round_num,
                        pick=overall_pick,
                        team_id=team_id,
                        team_name=team_name,
                        player_id=player.id,
                        player_name=player.name,
                        age=player.age,
                        position=player.position,
                        prospect_rating=rating,
                    )
                )

                overall_pick += 1

        return picks

    # -----------------------------------------------------------------------
    # Post-draft roster assignment
    # -----------------------------------------------------------------------

    # This code is generally overridden in the UI
    # It does run in cligr
    def _reassign_rosters(self, draft_order: list[dict]) -> None:
        """Re-run RosterAssigner for every team after the draft."""
        assigner = RosterAssigner()

        for team_entry in draft_order:
            team_id = team_entry["team_id"]

            player_ids = self.player_repo.get_player_ids_from_team_players(team_id)
            players = []
            for pid in player_ids:
                p = self.player_repo.look_up(pid)
                if p:
                    players.append(p)

            if not players:
                continue

            assignments = assigner.assign(players)
            self.status_repo.bulk_set(assignments)

        log.info("Reassigned rosters for %s teams", len(draft_order))
