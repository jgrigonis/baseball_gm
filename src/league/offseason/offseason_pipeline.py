# src/league/offseason/offseason_pipeline.py
import argparse
import csv
import datetime
import logging
from pathlib import Path
import random

from src.db.connection import get_connection
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.roster_trimmer import RosterTrimmer
from src.league.offseason.snake_draft import SnakeDraft
from src.util.locations import TEAM_FILES_DIR
from src.util.logger import setup_logger


class OffseasonPipeline:
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.player_status_repo = PlayerStatusRepository(conn)
        self.rng = rng or random.Random()
        # ...other repos as steps are built

    def run(self, season_id: str) -> None:
        print(f"season id: {season_id}")
        self._load_season_year(season_id)
        if not self._is_done(season_id, "archive"):
            if not self._playoffs_complete(season_id):
                print("❌ Playoffs are not complete — run play_playoffs.py first")
                return
            self._archive(season_id)
            self._mark_done(season_id, "archive")
        else:
            print("  Skipping archive (already done)")

        if not self._is_done(season_id, "age"):
            self._age(season_id, self.rng)
            self._mark_done(season_id, "age")
        else:
            print("  Skipping age (already done)")

        if not self._is_done(season_id, "retire"):
            self._retire(self.rng)
            self._mark_done(season_id, "retire")
        else:
            print("  Skipping retirement (already done)")

        if not self._is_done(season_id, "generate_draft"):
            self._generate_draft(season_id)
            self._mark_done(season_id, "generate_draft")
        else:
            print("  Skipping draft generation (already done)")

        if not self._is_done(season_id, "run_draft"):
            self._run_draft(season_id)
            self._mark_done(season_id, "run_draft")
        else:
            print("  Skipping run draft (already done)")
        if not self._is_done(season_id, "trim_rosters"):
            self._trim_rosters(season_id)
            self._mark_done(season_id, "trim_rosters")
        else:
            print("  Skipping roster trim (already done)")

        if not self._is_done(season_id, "reset_pitcher_state"):
            self._reset_pitcher_state()
            self._mark_done(season_id, "reset_pitcher_state")
        else:
            print("  Skipping pitcher state reset (already done)")

        if not self._is_done(season_id, "reset_player_energy"):
            self._reset_player_energy()
            self._mark_done(season_id, "reset_player_energy")
        else:
            print("  Skipping player energy reset (already done)")

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

    def _age(self, season_id, rng):
        """Step 2: Age every player by one year and write back updated skills."""
        cap_repo = TalentCapRepository(self.conn)
        energy_repo = PlayerEnergyRepository(self.conn)

        players = self.player_repo.get_all_players()

        # Batch-load all caps in one query
        player_ids = [p.id for p in players]
        all_caps = cap_repo.get_many(player_ids)

        for player in players:
            caps = all_caps.get(player.id)

            # Players who ended the season with very low energy aged harder —
            # either from injury or chronic overuse. Only affects coached/physical
            # skills via the coaching multiplier.
            energy_state = energy_repo.get(player.id)
            coaching = 1.0
            if energy_state is not None:
                games = energy_state.season_games_played
                result = self.conn.execute(
                    "SELECT COUNT(*) FROM player_injury_log WHERE player_id = ? AND season_id = ?",
                    (player.id, season_id),
                ).fetchone()
                injuries = result[0] if result else 0

                # Heavy usage wears players down over the season
                # 130+ games is a full workload — above that, physical aging accelerates
                if games >= 150:
                    coaching = 0.85  # extreme usage — 15% faster
                elif games >= 130:
                    coaching = 0.92  # heavy usage — 8% faster
                elif games >= 110:
                    coaching = 0.96  # moderate — 4% faster

                if injuries >= 2:
                    coaching = min(coaching, 0.80)
                elif injuries == 1:
                    coaching = min(coaching, 0.88)

                if energy_state.current_energy < 0.20:
                    coaching = min(coaching, 0.80)  # severe — 20% faster physical aging

            new_skills = player.skills.age_to(
                player.age + 1,
                from_age=player.age,
                rng=rng,
                caps=caps,
                coaching=coaching,
            )
            self.player_repo.update_skills(player.id, new_skills)

        print(f"  Aged {len(players)} players")

    def _retire(self, rng: random.Random) -> None:
        """Step 3: Evaluate all players for retirement, release retirees to free agency."""
        team_repo = TeamRepository(self.conn)

        players = self.player_repo.get_all_players()
        retired = []

        for player in players:
            current_status = self.player_status_repo.get_status(player.id)
            is_unrostered = current_status in ("prospect", "unassigned", "free_agent")
            # is_prospect = current_status in ("prospect", "unassigned")

            if self._should_retire(player.age, player.skills, is_unrostered, rng):
                self.player_status_repo.set_status(player.id, "free_agent")
                # Remove from team roster
                row = self.conn.execute(
                    "SELECT team_id FROM team_players WHERE player_id = ?", (player.id,)
                ).fetchone()
                if row:
                    team_repo.remove_player(row["team_id"], player.id)
                retired.append(player)

        # Write retired players to CSV
        if retired:
            out_dir = Path(TEAM_FILES_DIR) / str(self.year)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / "retired.csv"
            rows = [p.to_csv_dict() for p in retired]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"  Retired {len(retired)} players → {path}")
        else:
            print("  Retired 0 players")

    def _write_csvs(self, season_id: str) -> None:
        """Step 3: Write post-aging CSVs for every team into TEAM_FILES_DIR/YYYY/."""

        out_dir = Path(TEAM_FILES_DIR) / str(self.year)
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

    def _reset_player_energy(self) -> None:
        """Clear position player energy and injury counters between seasons."""
        repo = PlayerEnergyRepository(self.conn)
        count = repo.clear_season()
        print(f"  Cleared player energy for {count} players")

    def _reset_pitcher_state(self) -> None:
        """Clear all pitcher energy state between seasons."""
        from src.db.repositories.pitcher_state import PitcherStateRepository

        repo = PitcherStateRepository(self.conn)
        count = repo.clear_all()
        print(f"  Cleared pitcher state for {count} pitchers")

    def _generate_draft(self, season_id: str) -> None:
        """Generate prospect pool and write draft.csv."""
        generator = DraftGenerator(self.conn, self.rng)
        total = generator.run(season_id, self.year)
        print(f"  Draft pool ready: {total} draftable players")

    def _run_draft(self, season_id: str) -> None:
        """Run the draft."""
        draft = SnakeDraft(self.conn, self.rng)
        picks = draft.run(season_id, self.year)
        print(f"  Draft complete: {len(picks)} total picks")

    def _trim_rosters(self, season_id: str) -> None:

        trimmer = RosterTrimmer(self.conn)
        trimmer.run(season_id)

    @staticmethod
    def _should_retire(
        age: int, skills, is_unrostered: bool, rng: random.Random
    ) -> bool:
        if is_unrostered:
            if age < 18:
                return False
            probability = min(0.95, (age - 22) * 0.20)
        else:
            if age < 30:
                return False

            # Use role-appropriate skills for decline check
            # Pitchers: AC, ST, RE, GB, KK, CL
            # Position players: CT, PO, EY, SP, BR, AR, OF, IF, CA, CL
            pitching_skills = [
                "accuracy",
                "stamina",
                "recovery",
                "ground_balls",
                "strikes",
            ]
            batting_skills = [
                "contact",
                "power",
                "eye",
                "speed",
                "base_running",
                "arm",
                "outfield",
                "infield",
                "catching",
            ]

            skill_dict = skills.as_dict()
            is_pitcher = (
                skill_dict.get("stamina", 0) > 40 or skill_dict.get("strikes", 0) > 40
            )

            if is_pitcher:
                # Only physically declining skills — AC never declines so exclude it
                peak = max(
                    skill_dict.get(k, 0)
                    for k in ["strikes", "stamina", "recovery", "ground_balls"]
                )
                if peak >= 75:
                    return False
            else:
                # Only physically declining skills — CT/EY decline too late to be useful gates
                peak = max(skill_dict.get(k, 0) for k in ["power", "speed", "arm"])
                if peak >= 72:
                    return False

            if is_pitcher:
                relevant = {k: v for k, v in skill_dict.items() if k in pitching_skills}
            else:
                relevant = {k: v for k, v in skill_dict.items() if k in batting_skills}

            skill_avg = sum(relevant.values()) / len(relevant)
            if age < 35:
                base = (age - 30) * 0.03
            else:
                base = 0.15 + (age - 35) * 0.09  # steeper after 35
            decline_factor = max(0.0, (50 - skill_avg) / 100)
            probability = min(0.95, base + decline_factor)

        return rng.random() < probability

    def _load_season_year(self, season_id: str) -> int:
        """Fetch and cache the next season year (current year + 1)."""
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Season {season_id} not found")
        self.year = row["year"] + 1
        return self.year


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db", "-d", default="league.db")
    p.add_argument("--season-id", "-i", required=True)
    p.add_argument("--seed", "-s", type=int, help="Random seed for reproducibility")
    return p.parse_args()


def main():
    args = get_args()
    conn = get_connection(args.db)

    offseason_logger = setup_logger(
        name="offseason",
        level=logging.INFO,
        console_level=logging.WARNING,
        log_id="offseason",
        log_to_file=True,
    )

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    print(f"🎲 Seed: {seed}")
    offseason_logger.info(f"🎲 Offseason seed: {seed}")
    rng = random.Random(seed)

    pipeline = OffseasonPipeline(conn, rng)
    pipeline.run(args.season_id)


if __name__ == "__main__":
    main()
