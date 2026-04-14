# src/league/offseason/offseason_pipeline.py
import argparse
import csv
import datetime
import logging
from pathlib import Path
import random

from src.db.connection import get_connection
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.roster_trimmer import RosterTrimmer
from src.league.offseason.snake_draft import SnakeDraft
from src.league.offseason.build_season_stats import build_season, ensure_table
from src.util.locations import TEAM_FILES_DIR
from src.player.player_evaluator import PlayerEvaluator
from src.util.logger import setup_logger


class OffseasonPipeline:
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.player_status_repo = PlayerStatusRepository(conn)
        self.rng = rng or random.Random()
        self.league_id: str | None = None  # set in run()

    def run(self, season_id: str, league_id: str | None = None) -> None:
        print(f"season id: {season_id}")
        self.league_id = league_id
        self._current_season_id = season_id
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

        if not self._is_done(season_id, "clear_stale_prospects"):
            self._clear_stale_prospects()
            self._mark_done(season_id, "clear_stale_prospects")
        else:
            print("  Skipping stale prospect clear (already done)")

        if not self._is_done(season_id, "generate_draft"):
            self._generate_draft(season_id)
            self._mark_done(season_id, "generate_draft")
        else:
            print("  Skipping draft generation (already done)")

        if not self._is_done(season_id, "run_draft"):
            self._run_draft(season_id, league_id)
            self._mark_done(season_id, "run_draft")
        else:
            print("  Skipping run draft (already done)")

        if not self._is_done(season_id, "trim_rosters"):
            self._trim_rosters(season_id)
            self._mark_done(season_id, "trim_rosters")
        else:
            print("  Skipping roster trim (already done)")

        if not self._is_done(season_id, "reset_pitcher_state"):
            self._reset_pitcher_state(season_id)
            self._mark_done(season_id, "reset_pitcher_state")

        if not self._is_done(season_id, "rebuild_rotations"):
            self._rebuild_rotations(season_id)
            self._mark_done(season_id, "rebuild_rotations")
        else:
            print("  Skipping pitcher state reset (already done)")

        if not self._is_done(season_id, "reset_player_energy"):
            self._reset_player_energy()
            self._mark_done(season_id, "reset_player_energy")
        else:
            print("  Skipping player energy reset (already done)")

        if not self._is_done(season_id, "build_season_stats"):
            ensure_table(self.conn)
            n = build_season(self.conn, season_id)
            print(f"  Built season stats rollup: {n} rows")
            self._mark_done(season_id, "build_season_stats")
        else:
            print("  Skipping season stat rollup (already done)")

        if not self._is_done(season_id, "write_csvs"):
            self._write_csvs(season_id)
            self._mark_done(season_id, "write_csvs")
        else:
            print("  Skipping CSV export (already done)")

    def _archive(self, season_id: str) -> None:
        """Snapshot player skills at end of season, scoped to this league."""
        if self.league_id:
            players = self.player_repo.get_players_in_league_season(
                self.league_id, season_id
            )
        else:
            players = self.player_repo.get_all_players()
        for player in players:
            self.player_repo.snapshot_skills(player.id, season_id)
        self.conn.commit()

    def _age(self, season_id, rng):
        """Age every player by one year and write back updated skills.
        Scoped to players on teams in this league's season only."""
        cap_repo = TalentCapRepository(self.conn)
        energy_repo = PlayerEnergyRepository(self.conn)

        if self.league_id:
            players = self.player_repo.get_players_in_league_season(
                self.league_id, season_id
            )
        else:
            players = self.player_repo.get_all_players()
        player_ids = [p.id for p in players]
        all_caps = cap_repo.get_many(player_ids)

        for player in players:
            caps = all_caps.get(player.id)
            energy_state = energy_repo.get(player.id)
            coaching = 1.0
            if energy_state is not None:
                games = energy_state.season_games_played
                result = self.conn.execute(
                    "SELECT COUNT(*) FROM player_injury_log WHERE player_id = %s AND season_id = %s",
                    (player.id, season_id),
                ).fetchone()
                injuries = result[0] if result else 0

                if games >= 150:
                    coaching = 0.85
                elif games >= 130:
                    coaching = 0.92
                elif games >= 110:
                    coaching = 0.96

                if injuries >= 2:
                    coaching = min(coaching, 0.80)
                elif injuries == 1:
                    coaching = min(coaching, 0.88)

                if energy_state.current_energy < 0.20:
                    coaching = min(coaching, 0.80)

            new_skills = player.skills.age_to(
                player.age + 1,
                from_age=player.age,
                rng=rng,
                caps=caps,
                coaching=coaching,
            )
            self.player_repo.update_skills(player.id, new_skills)
        self.conn.commit()

        print(f"  Aged {len(players)} players")

    def _retire(self, rng: random.Random) -> None:
        """Evaluate all players for retirement.
        Scoped to players on teams in this league's season only."""
        team_repo = TeamRepository(self.conn)
        if self.league_id:
            players = self.player_repo.get_players_in_league_season(
                self.league_id, self._current_season_id
            )
        else:
            players = self.player_repo.get_all_players()
        retired = []

        for player in players:
            current_status = self.player_status_repo.get_status(player.id)
            is_unrostered = current_status in ("prospect", "unassigned", "free_agent")

            if self._should_retire(player.age, player.skills, is_unrostered, rng):
                self.player_status_repo.set_status(player.id, "free_agent")
                row = self.conn.execute(
                    "SELECT team_id FROM team_players WHERE player_id = %s",
                    (player.id,),
                ).fetchone()
                if row:
                    team_repo.remove_player(row["team_id"], player.id)
                retired.append(player)

        self.conn.commit()

        if retired:
            if self.league_id:
                out_dir = Path(TEAM_FILES_DIR) / str(self.year) / self.league_id
            else:
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
        """Write post-aging CSVs for teams in this league only."""
        # Scope to this league via league_season_teams
        if self.league_id:
            teams = self.conn.execute(
                """SELECT t.id, t.source_csv
                   FROM teams t
                   JOIN league_season_teams lst ON lst.team_id = t.id
                   WHERE lst.season_id = %s AND lst.league_id = %s""",
                (season_id, self.league_id),
            ).fetchall()
            out_dir = Path(TEAM_FILES_DIR) / str(self.year) / self.league_id
        else:
            teams = self.conn.execute(
                """SELECT t.id, t.source_csv
                   FROM teams t
                   JOIN league_season_teams lst ON lst.team_id = t.id
                   WHERE lst.season_id = %s""",
                (season_id,),
            ).fetchall()
            out_dir = Path(TEAM_FILES_DIR) / str(self.year)

        out_dir.mkdir(parents=True, exist_ok=True)

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
            "SELECT 1 FROM offseason_steps WHERE season_id = %s AND step = %s",
            (season_id, step),
        ).fetchone()
        return row is not None

    def _mark_done(self, season_id: str, step: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO offseason_steps (season_id, step, completed_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (season_id, step, now),
        )
        self.conn.commit()

    def _playoffs_complete(self, season_id: str) -> bool:
        finals = self.conn.execute(
            "SELECT id FROM series WHERE season_id = %s AND name = 'Finals'",
            (season_id,),
        ).fetchone()
        if finals is None:
            return False
        row = self.conn.execute(
            """SELECT COUNT(*) AS wins FROM games
               WHERE series_id = %s AND completed = 1
               GROUP BY winner_id ORDER BY wins DESC LIMIT 1""",
            (finals["id"],),
        ).fetchone()
        return row is not None and row["wins"] >= 4

    def _reset_player_energy(self) -> None:
        repo = PlayerEnergyRepository(self.conn)
        count = repo.clear_season()
        print(f"  Cleared player energy for {count} players")

    def _clear_stale_prospects(self) -> None:
        """
        Clear undrafted prospects who are too old to realistically be drafted.
        Prospects aged 24+ who are still in the pool get marked free_agent
        so they don't accumulate indefinitely across seasons.
        """
        rows = self.conn.execute("""
            SELECT p.id
            FROM players p
            JOIN player_status ps ON p.id = ps.player_id
            LEFT JOIN team_players tp ON p.id = tp.player_id
            WHERE ps.status = 'prospect'
              AND tp.player_id IS NULL
            """).fetchall()

        cleared = 0
        for row in rows:
            player = self.player_repo.look_up(row["id"])
            if player and player.age >= 24:
                self.player_status_repo.set_status(player.id, "free_agent")
                cleared += 1

        if cleared:
            self.conn.commit()
        print(f"  Cleared {cleared} stale prospects (age >= 24)")

    def _reset_pitcher_state(self, season_id: str) -> None:
        repo = PitcherStateRepository(self.conn)
        count = repo.clear_all_pitcher_state()
        print(f"  Cleared pitcher state for {count} pitchers")
        self._reset_rotation_pointers(season_id)

    def _rebuild_rotations(self, season_id: str) -> None:
        """
        Rebuild starting rotations and bullpen roles for all teams at the start
        of a new season. Picks the top 5 healthy pitchers by SP rating per team.
        Respects 26-man roster only (same as bootstrap).
        """
        # rot_repo = TeamRotationsRepository(self.conn)
        status_repo = self.player_status_repo
        inj_repo = InjuryRepository(self.conn, league_id=self.league_id or "")
        team_repo = TeamRepository(self.conn)
        bp_repo = BullpenRepository(self.conn)

        teams = team_repo.get_teams_by_season(season_id)
        injured_ids = {inj.player_id for inj in inj_repo.get_all_injured()}
        today = datetime.date.today().isoformat()
        rebuilt = 0

        for team in teams:
            if not team:
                continue

            # 26-man players only
            active_ids = set(status_repo.get_by_team_and_status(team.id, "26man"))
            active_players = [p for p in team.players if p.id in active_ids]

            # Pick top 5 healthy starters directly
            pitchers = [
                p for p in active_players if p.is_pitcher() and p.id not in injured_ids
            ]
            pitchers.sort(
                key=lambda p: PlayerEvaluator.rate_player(p.skills).get("sp", 0),
                reverse=True,
            )
            rotation = [p.id for p in pitchers[:5]]
            if not rotation:
                print(
                    f"  Warning: No healthy pitchers for {team.name}, skipping rotation rebuild."
                )
                continue

            # Replace old rotation rows with fresh ones
            self.conn.execute(
                "DELETE FROM team_rotations WHERE team_id = %s AND season_id = %s",
                (team.id, season_id),
            )
            for order, pid in enumerate(rotation, 1):
                self.conn.execute(
                    """INSERT INTO team_rotations
                           (team_id, season_id, player_id, rotation_order, effective_date)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (team.id, season_id, pid, order, today),
                )

            # Reset pointer to SP1
            self.conn.execute(
                """INSERT INTO team_rotation_pointer
                       (team_id, season_id, series_id, next_order, updated_at)
                   VALUES (%s, %s, '', 1, NOW())
                   ON CONFLICT (team_id, season_id, series_id)
                   DO UPDATE SET next_order = 1, updated_at = NOW()""",
                (team.id, season_id),
            )

            # Rebuild bullpen roles from the active 26-man non-rotation pitchers
            relievers = [
                p
                for p in active_players
                if p.is_pitcher() and p.id not in set(rotation)
            ]
            roles = team.set_bullpen_roles(rotation, relievers=relievers)
            if roles:
                bp_repo.set_roles(team.id, season_id, roles, today)

            rebuilt += 1

        self.conn.commit()
        print(f"  Rebuilt rotations and bullpen roles for {rebuilt} teams")

    def _reset_rotation_pointers(self, season_id: str) -> None:
        rot_repo = TeamRotationsRepository(self.conn)
        reset = rot_repo.reset_rotation_pointers(season_id)
        self.conn.commit()
        print(f"  Reset rotation pointers to sp1 for {reset} teams")

    def _generate_draft(self, season_id: str) -> None:
        generator = DraftGenerator(self.conn, self.rng)
        total = generator.run(season_id, self.year, league_id=self.league_id)
        print(f"  Draft pool ready: {total} draftable players")

    def _write_draft_order(
        self, season_id: str, league_id: str, draft_order: list[dict]
    ) -> None:
        """Persist the draft order and pick rights for this draft."""
        from src.league.offseason.snake_draft import write_draft_order

        # The draft record belongs to the NEW season (created by offseason_service),
        # not the completed season passed in as season_id. Find the newest pending draft.
        row = self.conn.execute(
            """SELECT id FROM drafts WHERE league_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        if not row:
            print("  WARNING: no draft record found, skipping draft_order write")
            return

        ordered_ids = [e["team_id"] for e in draft_order]
        write_draft_order(self.conn, row["id"], league_id, self.year, ordered_ids)
        print(f"  Draft order stored: {len(draft_order)} teams")

    def _run_draft(self, season_id: str, league_id: str) -> None:
        snake = SnakeDraft(self.conn, self.rng)
        # Build order first so we can persist it before the draft runs
        draft_order = snake._build_draft_order(season_id)
        self._write_draft_order(season_id, league_id, draft_order)
        picks = snake.run_snake_draft_with_order(draft_order, self.year, league_id)
        print(f"  Draft complete: {len(picks)} total picks")

    def _trim_rosters(self, season_id: str) -> None:
        trimmer = RosterTrimmer(self.conn)
        trimmer.run(season_id)

    @staticmethod
    def _should_retire(age, skills, is_unrostered, rng):
        if is_unrostered:
            if age < 18:
                return False
            probability = min(0.95, (age - 22) * 0.20)
        else:
            if age < 30:
                return False
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
                peak = max(
                    skill_dict.get(k, 0)
                    for k in ["strikes", "stamina", "recovery", "ground_balls"]
                )
                if peak >= 75:
                    return False
            else:
                peak = max(skill_dict.get(k, 0) for k in ["power", "speed", "arm"])
                if peak >= 72:
                    return False
            relevant_keys = pitching_skills if is_pitcher else batting_skills
            relevant = {k: v for k, v in skill_dict.items() if k in relevant_keys}
            skill_avg = sum(relevant.values()) / len(relevant)
            if age < 35:
                base = (age - 30) * 0.03
            else:
                base = 0.15 + (age - 35) * 0.09
            decline_factor = max(0.0, (50 - skill_avg) / 100)
            probability = min(0.95, base + decline_factor)
        return rng.random() < probability

    def _load_season_year(self, season_id: str) -> int:
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Season {season_id} not found")
        self.year = row["year"] + 1
        return self.year


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--season-id", "-i", required=True)
    p.add_argument("--league-id", "-l", default=None)
    p.add_argument("--seed", "-s", type=int)
    return p.parse_args()


def main():
    args = get_args()
    conn = get_connection()

    setup_logger(
        name="offseason",
        level=logging.INFO,
        console_level=logging.WARNING,
        log_id="offseason",
        log_to_file=True,
    )

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    print(f"🎲 Seed: {seed}")
    rng = random.Random(seed)

    pipeline = OffseasonPipeline(conn, rng)
    pipeline.run(args.season_id, league_id=args.league_id)


if __name__ == "__main__":
    main()
