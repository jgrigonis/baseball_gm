# src/league/offseason_pipeline.py
import argparse
import csv
import datetime
from pathlib import Path
import random
import sqlite3


from src.util.locations import LEAGUE_FILES_DIR, TEAM_FILES_DIR
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository


class OffseasonPipeline:
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.player_status_repo = PlayerStatusRepository(conn)
        self.rng = rng or random.Random()
        # ...other repos as steps are built

    def run(self, season_id: str) -> None:
        print(f"season id: {season_id}")
        if not self._is_done(season_id, "archive"):
            if not self._playoffs_complete(season_id):
                print("❌ Playoffs are not complete — run play_playoffs.py first")
                return
            self._archive(season_id)
            self._mark_done(season_id, "archive")
        else:
            print("  Skipping archive (already done)")

        if not self._is_done(season_id, "age"):
            self._age(self.rng)
            self._mark_done(season_id, "age")
        else:
            print("  Skipping age (already done)")

        if not self._is_done(season_id, "retire"):
            self._retire(self.rng)
            self._mark_done(season_id, "retire")
        else:
            print("  Skipping retirement (already done)")

        if not self._is_done(season_id, "reset_pitcher_state"):
            self._reset_pitcher_state()
            self._mark_done(season_id, "reset_pitcher_state")
        else:
            print("  Skipping pitcher state reset (already done)")

        if not self._is_done(season_id, "write_csvs"):
            self._write_csvs(season_id)
            self._mark_done(season_id, "write_csvs")
        else:
            print("  Skipping CSV export (already done)")

    def _archive(self, season_id: str) -> None:
        """Step 1: Snapshot all player skills at end of season."""
        players = self.player_repo.get_all_players()
        for player in players:
            self.player_repo.snapshot_skills(player.id, season_id)
        # aggregate_season_stats(season_id)  — TBD

    def _age(self, rng: random.Random) -> None:
        """Step 2: Age every player by one year and write back updated skills."""
        # Setup RNG

        players = self.player_repo.get_all_players()
        for player in players:
            new_skills = player.skills.age_to(player.age + 1, rng=rng)
            self.player_repo.update_skills(player.id, new_skills)
        print(f"  Aged {len(players)} players")

    def _retire(self, rng: random.Random) -> None:
        """Step 3: Evaluate all players for retirement, release retirees to free agency."""
        team_repo = TeamRepository(self.conn)

        players = self.player_repo.get_all_players()
        retired = []

        for player in players:
            current_status = self.player_status_repo.get_status(player.id)
            is_prospect = current_status in ("prospect", "unassigned")

            if self._should_retire(player.age, player.skills, is_prospect, rng):
                self.player_status_repo.set_status(player.id, "free_agent")
                # Remove from team roster
                row = self.conn.execute(
                    "SELECT team_id FROM team_players WHERE player_id = ?", (player.id,)
                ).fetchone()
                if row:
                    team_repo.remove_player(row["team_id"], player.id)
                retired.append(player)

        print(f"  Retired {len(retired)} players")

    def _write_csvs(self, season_id: str) -> None:
        """Step 3: Write post-aging CSVs for every team into TEAM_FILES_DIR/YYYY/."""

        # Get the year from the season record
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Season {season_id} not found")
        year = row["year"] + 1

        out_dir = Path(TEAM_FILES_DIR) / str(year)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Get all teams with their players
        teams = self.conn.execute("SELECT id, source_csv FROM teams").fetchall()

        for team in teams:
            players = self.player_repo.get_players_by_team(team["id"])
            if not players:
                continue

            filename = (
                Path(team["source_csv"]).name
                if team["source_csv"]
                else f"{team['id']}.csv"
            )
            path = out_dir / filename
            if path.exists():
                print(f"  Skipping {path} (already exists)")
                continue

            rows = [p.to_csv_dict() for p in players]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            print(f"  Wrote {path}")

    def _is_done(self, season_id: str, step: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM offseason_steps WHERE season_id = ? AND step = ?",
            (season_id, step),
        ).fetchone()
        return row is not None

    def _mark_done(self, season_id: str, step: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO offseason_steps (season_id, step, completed_at) VALUES (?, ?, ?)",
            (season_id, step, now),
        )
        self.conn.commit()

    def _playoffs_complete(self, season_id: str) -> bool:
        """Check if a team has clinched the Finals."""
        finals = self.conn.execute(
            "SELECT id FROM series WHERE season_id = ? AND name = 'Finals'",
            (season_id,),
        ).fetchone()

        if finals is None:
            return False

        # Check if any team has 4 wins in the Finals
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS wins
            FROM games
            WHERE series_id = ? AND completed = 1
            GROUP BY winner_id
            ORDER BY wins DESC
            LIMIT 1
            """,
            (finals["id"],),
        ).fetchone()

        return row is not None and row["wins"] >= 4

    def _reset_pitcher_state(self) -> None:
        """Clear all pitcher energy state between seasons."""
        from src.db.repositories.pitcher_state import PitcherStateRepository

        repo = PitcherStateRepository(self.conn)
        count = repo.clear_all()
        print(f"  Cleared pitcher state for {count} pitchers")

    @staticmethod
    def _should_retire(age: int, skills, is_prospect: bool, rng: random.Random) -> bool:
        """
        Decide if a player retires this offseason.

        Rostered players:
          - No chance before 30
          - 4% per year over 30, accelerated by skill decline below 50 avg

        Prospects/unassigned:
          - No chance before 22
          - 20% per year over 22 — ages out quickly if never drafted
        """
        if is_prospect:
            if age < 22:
                return False
            probability = min(0.95, (age - 22) * 0.20)
        else:
            if age < 30:
                return False
            skill_avg = sum(skills.as_dict().values()) / len(skills.as_dict())
            base = (age - 30) * 0.04
            decline_factor = max(0.0, (50 - skill_avg) / 100)
            probability = min(0.95, base + decline_factor)

        return rng.random() < probability


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db", "-d", default="league.db")
    p.add_argument("--season-id", "-i", required=True)
    p.add_argument("--seed", "-s", type=int, help="Random seed for reproducibility")
    return p.parse_args()


def main():
    args = get_args()
    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / args.db)
    conn.row_factory = sqlite3.Row

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    print(f"🎲 Seed: {seed}")
    rng = random.Random(seed)

    pipeline = OffseasonPipeline(conn, rng)
    pipeline.run(args.season_id)


if __name__ == "__main__":
    main()
