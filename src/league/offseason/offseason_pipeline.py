# src/league/offseason_pipeline.py
import argparse
import csv
import datetime
from pathlib import Path
import random
import sqlite3


from src.util.locations import LEAGUE_FILES_DIR, TEAM_FILES_DIR
from src.db.repositories.player_repo import PlayerRepository

class OffseasonPipeline:
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
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
            new_age = int(player.age) + 1
            new_skills = player.skills.age_to(new_age, rng=rng)
            self.player_repo.update_age(player.id, new_age)
            self.player_repo.update_skills(player.id, new_skills)
        print(f"  Aged {len(players)} players")

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

            filename = Path(team["source_csv"]).name if team["source_csv"] else f"{team['id']}.csv"
            path = out_dir / filename

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
