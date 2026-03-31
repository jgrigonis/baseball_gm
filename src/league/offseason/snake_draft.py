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

import csv
import random
from dataclasses import dataclass
from pathlib import Path

from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord
from src.team.roster_assigner import RosterAssigner
from src.util.locations import TEAM_FILES_DIR

ROUNDS = 20


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
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.rng = rng or random.Random()
        self.player_repo = PlayerRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)

    def run(self, season_id: str, year: int, league_id: str | None = None) -> list[DraftPick]:
        """
        Execute the snake draft.

        Args:
            season_id: The season that just ended (for standings)
            year: Draft year (for output path)

        Returns:
            List of DraftPick results
        """
        # 1. Build draft order (worst record first)
        draft_order = self._build_draft_order(season_id)
        print(f"  Draft order: {len(draft_order)} teams")

        # 2. Load draft pool — all players with status 'prospect' and no team
        pool = self._load_draft_pool()
        print(f"  Draft pool: {len(pool)} players available")

        if not pool:
            print("  WARNING: Empty draft pool, skipping draft")
            return []

        # 3. Pre-compute prospect ratings
        rated = self._rate_pool(pool)

        # 4. Run snake draft
        picks = self._run_snake(draft_order, rated)
        print(f"  Completed {len(picks)} picks across {ROUNDS} rounds")

        # 5. Re-run RosterAssigner for each team
        self._reassign_rosters(draft_order)

        # 6. Write draft results CSV
        self._write_results(picks, year, league_id)

        return picks

    # -----------------------------------------------------------------------
    # Draft order
    # -----------------------------------------------------------------------

    def _build_draft_order(self, season_id: str) -> list[dict]:
        # Get all teams in this season with city/mascot in one query
        all_team_rows = self.conn.execute(
            """
            SELECT DISTINCT lst.team_id, t.city, t.mascot
            FROM league_season_teams lst
            JOIN teams t ON lst.team_id = t.id
            WHERE lst.season_id = ?
            """,
            (season_id,),
        ).fetchall()

        # Get win% per team
        stat_rows = self.conn.execute(
            """
            SELECT tgs.team_id,
                COALESCE(SUM(tgs.win),  0) AS wins,
                COALESCE(SUM(tgs.loss), 0) AS losses
            FROM team_game_stats tgs
            JOIN games g ON tgs.game_id = g.id
            WHERE g.season_id    = ?
            AND g.completed    = 1
            AND g.series_id IS NULL
            GROUP BY tgs.team_id
            ORDER BY wins DESC, losses ASC
            """,
            (season_id,),
        ).fetchall()

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
            print(f"WARNING: There are no teams with games in season {season_id}")

        teams_with_games.sort(key=lambda t: t["win_pct"])
        return teams_with_games + teams_without_games

    # -----------------------------------------------------------------------
    # Draft pool
    # -----------------------------------------------------------------------

    def _load_draft_pool(self) -> list[PlayerRecord]:
        """Load all prospect players not on any team."""
        rows = self.conn.execute("""
            SELECT p.id
            FROM players p
            JOIN player_status ps ON p.id = ps.player_id
            LEFT JOIN team_players tp ON p.id = tp.player_id
            WHERE ps.status = 'prospect'
              AND tp.player_id IS NULL
            """).fetchall()

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
        # n_teams = len(draft_order)
        picks = []
        overall_pick = 1

        # available pool as ordered list — pop from front (best first)
        available = list(rated)

        for round_num in range(1, ROUNDS + 1):
            # Odd rounds: worst→best, even rounds: best→worst (snake)
            if round_num % 2 == 1:
                order = draft_order
            else:
                order = list(reversed(draft_order))

            for team_entry in order:
                if not available:
                    print(f"  Draft pool exhausted at pick {overall_pick}")
                    return picks

                player, rating = available.pop(0)
                team_id = team_entry["team_id"]
                team_name = team_entry["team_name"]

                # Add to team_players
                self.conn.execute(
                    "INSERT OR IGNORE INTO team_players (team_id, player_id) VALUES (?, ?)",
                    (team_id, player.id),
                )
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

        self.conn.commit()
        return picks

    # -----------------------------------------------------------------------
    # Post-draft roster assignment
    # -----------------------------------------------------------------------

    def _reassign_rosters(self, draft_order: list[dict]) -> None:
        """Re-run RosterAssigner for every team after the draft."""
        assigner = RosterAssigner()

        for team_entry in draft_order:
            team_id = team_entry["team_id"]

            player_ids = self.conn.execute(
                "SELECT player_id FROM team_players WHERE team_id = ?",
                (team_id,),
            ).fetchall()

            players = []
            for row in player_ids:
                p = self.player_repo.look_up(row["player_id"])
                if p:
                    players.append(p)

            if not players:
                continue

            assignments = assigner.assign(players)
            self.status_repo.bulk_set(assignments)

        print(f"  Reassigned rosters for {len(draft_order)} teams")

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------

    def _write_results(self, picks: list[DraftPick], year: int, league_id: str | None = None) -> None:
        """Write draft_results.csv."""
        out_dir = Path(TEAM_FILES_DIR) / str(year)
        if league_id:
            out_dir = Path(TEAM_FILES_DIR) / str(year) / league_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "draft_results.csv"

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Round",
                    "Pick",
                    "Team",
                    "Player",
                    "Age",
                    "Position",
                    "Prospect Rating",
                ],
            )
            writer.writeheader()
            for p in picks:
                writer.writerow(
                    {
                        "Round": p.round,
                        "Pick": p.pick,
                        "Team": p.team_name,
                        "Player": p.player_name,
                        "Age": p.age,
                        "Position": p.position,
                        "Prospect Rating": p.prospect_rating,
                    }
                )

        print(f"  Wrote {out_path}")
