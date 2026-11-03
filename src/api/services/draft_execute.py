# src/api/services/draft_execute.py
#
# Blitz draft. Subclasses SnakeDraft and overrides _run_snake so that each
# team picks by its draft strategy (pins, then need chips).
# A team with no saved strategy, which includes every AI team, drafts by
# the needs its roster suggests; an AI team's state and persona weigh them
# (src/league/front_office.py). Afterwards each AI team picks its 26-man and
# 40-man, and trims its minors, leaning young or veteran as its outlook says.

from __future__ import annotations

import logging
import random
from datetime import datetime, UTC

from src.api.services import front_office, trades
from src.api.services.draft_needs import draft_strategies
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.offseason_repo import OffseasonRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.rotation_seeder import seed_ai_rotations
from src.league.offseason.draft_strategy import DraftStrategy, StrategyScorer
from src.league.offseason.snake_draft import SnakeDraft, DraftPick, ROUNDS
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.team.roster_assigner import RosterAssigner
from src.league.league_constants import LEAGUE_START_YEAR

log = logging.getLogger(__name__)


class BlitzDraft(SnakeDraft):
    """
    Snake draft variant for blitz leagues.

    Each team picks by its draft strategy. A team without one takes the
    best prospect rating, as the base SnakeDraft does.
    """

    def __init__(
        self,
        conn,
        league_id: str,
        human_team_ids: set[str],
        rng=None,
        gm_strategies: dict[str, DraftStrategy] | None = None,
        outlooks: dict[str, front_office.Outlook] | None = None,
    ):
        """
        Args:
            conn: DB connection
            league_id: League to scope the draft pool to
            human_team_ids: Teams a person runs. Their picks aren't auto
                            picks, and they set their own rosters after.
            gm_strategies: { team_id: DraftStrategy } for each team.
            outlooks: { team_id: Outlook } for AI teams, for their rosters.
        """
        super().__init__(conn, league_id, rng)
        self._human_team_ids = set(human_team_ids)
        # Copied: chip levels wear off as picks are made
        self._strategies: dict[str, DraftStrategy] = {
            tid: s.copy() for tid, s in (gm_strategies or {}).items()
        }
        self._outlooks = outlooks or {}

    def _run_snake(
        self,
        draft_order: list[dict],
        rated: list[tuple[PlayerRecord, int]],
    ) -> list[DraftPick]:
        """Override: pick by each team's draft strategy."""
        picks = []
        overall_pick = 1
        available: set[str] = {p.id for p, _ in rated}
        fallback: list[tuple[PlayerRecord, int]] = list(rated)
        by_id = {p.id: p for p, _ in rated}
        scorer = StrategyScorer(rated) if self._strategies and rated else None
        names = {t["team_id"]: t["team_name"] for t in draft_order}

        for round_num in range(1, ROUNDS + 1):
            order = draft_order if round_num % 2 == 1 else list(reversed(draft_order))

            for team_entry in order:
                if not available:
                    log.info("Draft pool exhausted at pick %s", overall_pick)
                    return picks

                # The pick's owner makes it: it may have been traded.
                team_id = self._owner(round_num, team_entry["team_id"])

                chosen: PlayerRecord | None = None
                strategy = self._strategies.get(team_id)
                if strategy is not None:
                    pid = scorer.choose(available, strategy)
                    chosen = by_id.get(pid) if pid else None

                if chosen is None:
                    for player, _ in fallback:
                        if player.id in available:
                            chosen = player
                            break

                if chosen is None:
                    break

                available.discard(chosen.id)
                if strategy is not None:
                    scorer.wear_off(chosen.id, strategy)
                rating = PlayerEvaluator.prospect_rating(chosen.skills)
                tr = TeamRepository(self.conn)
                tr.add_player(team_id, chosen.id)
                self.status_repo.set_status(chosen.id, "minors")

                picks.append(
                    DraftPick(
                        round=round_num,
                        pick=overall_pick,
                        team_id=team_id,
                        team_name=names.get(team_id, ""),
                        player_id=chosen.id,
                        player_name=chosen.name,
                        age=chosen.age,
                        position=chosen.position,
                        prospect_rating=rating,
                    )
                )

                overall_pick += 1

        self.conn.commit()
        return picks

    def _reassign_rosters(self, draft_order: list[dict]) -> None:
        """Only reassign AI-managed teams — human GMs set their own roster."""
        assigner = RosterAssigner()
        ai_teams = [t for t in draft_order if t["team_id"] not in self._human_team_ids]

        for team_entry in ai_teams:
            team_id = team_entry["team_id"]
            player_ids = self.player_repo.get_player_ids_from_team_players(team_id)
            players = []
            for pid in player_ids:
                p = self.player_repo.look_up(pid)
                if p:
                    players.append(p)
            if not players:
                continue
            outlook = self._outlooks.get(team_id)
            bonus = outlook.age_bonus(players) if outlook else None
            assignments = assigner.assign(players, bonus)
            self.status_repo.bulk_set(assignments)

        log.info("Reassigned rosters for %s AI teams", len(ai_teams))


def execute_blitz_draft(draft_id: str, conn) -> dict:
    """
    Run the full blitz draft end-to-end.
    Assumes DraftGenerator has already been run (prospect pool exists).
    """
    dr = DraftRepository(conn)
    draft = dr.get_draft(draft_id)

    if not draft:
        raise ValueError(f"Draft {draft_id} not found.")
    if draft["state"] != "pending":
        raise ValueError(f"Draft is already in state '{draft['state']}'.")
    if draft["format"] != "preference":
        raise ValueError("execute_blitz_draft only handles preference-format drafts.")

    league_id = draft["league_id"]
    season_id = draft["season_id"]

    dr.set_draft_state(draft_id, "open")

    # Load all human GM team IDs first
    gm_repo = GMRepository(conn)
    human_team_ids = gm_repo.get_human_team_ids(league_id)

    # Every team drafts by its saved strategy or, failing that, its needs
    gm_strategies = draft_strategies(conn, draft_id, league_id, cached=False)

    sr = SeasonRepository(conn)
    row = sr.get_year(season_id)
    year = row["year"] if row else LEAGUE_START_YEAR

    # Read the pre-stored draft order from draft_order table (written by
    # league_start or offseason_pipeline — never recompute from standings here)
    stored_order = dr.get_team_id_draft_order(draft_id)

    outlooks = front_office.outlooks(conn, league_id, season_id)
    blitz = BlitzDraft(
        conn,
        league_id=league_id,
        human_team_ids=human_team_ids,
        gm_strategies=gm_strategies,
        outlooks=outlooks,
    )

    if stored_order:
        draft_order = [{"team_id": r["team_id"], "team_name": ""} for r in stored_order]
        picks = blitz.run_snake_draft_with_order(draft_order, year, league_id)
    else:
        raise RuntimeError("No stored order found")

    # Record into draft_picks table
    now = datetime.now(UTC).isoformat()
    for pick in picks:
        gm_id = gm_repo.get_gm_id_from_team_id(league_id, pick.team_id)
        # gm_id = _gm_for_team(conn, league_id, pick.team_id)
        auto = pick.team_id not in human_team_ids
        dr.insert_draft_picks(
            draft_id,
            pick.pick,
            pick.round,
            gm_id,
            pick.team_id,
            pick.player_id,
            auto,
            now,
        )

    dr.set_complete_current_pick(draft_id, len(picks) + 1)
    # Offers with this draft's picks in them have nothing left to trade.
    trades.draft_run(conn, league_id, year)

    # Seed rotations/bullpen for AI teams using full post-draft roster.
    # Human teams are excluded — they set their own lineups.
    ai_team_ids = {r["team_id"] for r in stored_order} - human_team_ids
    seeded = seed_ai_rotations(
        conn,
        season_id,
        ai_team_ids,
        statuses=["26man", "40man"],
        effective_date=f"{year}-04-01",
        league_id=league_id,
    )
    log.info("Seeded rotations for %s AI teams post-draft.", seeded)

    lr = LeagueRepository(conn)
    lr.set_state(league_id, "preseason")

    # Run post-draft pipeline steps (trim rosters, rotations, energy, stats, csvs).
    # These were deferred so they run against the final rosters including draft picks.
    osr = OffseasonRepository(conn)
    prev_season_id = osr.find_season_with_offseason_steps(league_id, season_id)
    if prev_season_id:
        log.info("Running post-draft pipeline steps for season %s...", prev_season_id)
        tilts = {tid: o.tilt for tid, o in outlooks.items()}
        pipeline = OffseasonPipeline(conn, random.Random(), tilts=tilts)
        pipeline.run(prev_season_id, league_id=league_id, skip_auto_draft=True)

    # Rookie deals for the draft class, and new deals for anyone whose last
    # one ran out with the old season (src/player/contracts.py).
    ContractRepository(conn).sign_unsigned(league_id, year)

    return {
        "draft_id": draft_id,
        "season_id": season_id,
        "picks_made": len(picks),
        "auto_picks": sum(1 for p in picks if p.team_id not in human_team_ids),
        "rounds": ROUNDS,
        "league_state": "preseason",
    }
