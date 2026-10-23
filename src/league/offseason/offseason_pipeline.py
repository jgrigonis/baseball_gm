# src/league/offseason/offseason_pipeline.py
import argparse
import csv
import datetime
import logging
from pathlib import Path
import random

from src.db.connection import get_connection
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.offseason_repo import OffseasonRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.retirement_repo import RetirementRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.talent_cap_repo import TalentCapRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.league_constants import SEASON_LENGTH
from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.roster_trimmer import RosterTrimmer
from src.league.offseason.snake_draft import SnakeDraft, write_draft_order
from src.league.offseason.build_season_stats import build_season
from src.league.rotation_seeder import seed_ai_rotations
from src.player.player_skills import PlayerSkills
from src.util.locations import TEAM_FILES_DIR
from src.util.logger import configure_app_logging, setup_logger

log = logging.getLogger(__name__)


class OffseasonPipeline:
    def __init__(self, conn, rng: random.Random | None = None):
        self.conn = conn
        self.player_repo = PlayerRepository(conn)
        self.player_status_repo = PlayerStatusRepository(conn)
        self.draft_repo = DraftRepository(conn)
        self.season_repo = SeasonRepository(conn)
        self.os_repo = OffseasonRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.rng = rng or random.Random()
        self.league_id: str | None = None  # set in run()

    def run(
        self,
        season_id: str,
        league_id: str,
        skip_auto_draft: bool = False,
        stop_after_draft_gen: bool = False,
    ) -> None:
        log.info("season id: %s", season_id)
        self.league_id = league_id
        self._current_season_id = season_id
        row = self.season_repo.get_year(season_id)
        if row:
            self.year = row["year"] + 1
        else:
            log.warning("No year found with season.")
            self.year = 2025

        if not self.os_repo.is_done(season_id, "archive"):
            if not self._playoffs_complete(season_id):
                log.warning("Playoffs are not complete — run play_playoffs.py first")
                return
            self._archive(season_id)
            self._mark_done(season_id, "archive")
        else:
            log.info("Skipping archive (already done)")

        if not self.os_repo.is_done(season_id, "age"):
            self._age(season_id, self.rng)
            self._mark_done(season_id, "age")
        else:
            log.info("Skipping age (already done)")

        if not self.os_repo.is_done(season_id, "retire"):
            self._retire(self.rng)
            self._mark_done(season_id, "retire")
        else:
            log.info("Skipping retirement (already done)")

        if not self.os_repo.is_done(season_id, "clear_stale_prospects"):
            self._clear_stale_prospects()
            self._mark_done(season_id, "clear_stale_prospects")
        else:
            log.info("Skipping stale prospect clear (already done)")

        if not self.os_repo.is_done(season_id, "generate_draft"):
            self._generate_draft(season_id)
            self._mark_done(season_id, "generate_draft")
        else:
            log.info("Skipping draft generation (already done)")

        if stop_after_draft_gen:
            log.info("Stopping after draft generation (post-draft steps deferred)")
            return

        if skip_auto_draft:
            log.info("Skipping auto-draft (UI draft will run separately)")
        elif not self.os_repo.is_done(season_id, "run_draft"):
            self._run_draft(season_id, league_id)
            self._mark_done(season_id, "run_draft")
        else:
            log.info("Skipping run draft (already done)")

        if not self.os_repo.is_done(season_id, "trim_rosters"):
            self._trim_rosters(season_id)
            self._mark_done(season_id, "trim_rosters")
        else:
            log.info("Skipping roster trim (already done)")

        if not self.os_repo.is_done(season_id, "reset_pitcher_state"):
            self._reset_pitcher_state(season_id)
            self._mark_done(season_id, "reset_pitcher_state")

        if not self.os_repo.is_done(season_id, "rebuild_rotations"):
            self._rebuild_rotations(season_id)
            self._mark_done(season_id, "rebuild_rotations")
        else:
            log.info("Skipping pitcher state reset (already done)")

        if not self.os_repo.is_done(season_id, "reset_player_energy"):
            self._reset_player_energy()
            self._mark_done(season_id, "reset_player_energy")
        else:
            log.info("Skipping player energy reset (already done)")

        if not self.os_repo.is_done(season_id, "build_season_stats"):
            n = build_season(self.conn, season_id)
            log.info("Built season stats rollup: %s rows", n)
            self._mark_done(season_id, "build_season_stats")
        else:
            log.info("Skipping season stat rollup (already done)")

        if not self.os_repo.is_done(season_id, "write_csvs"):
            self._write_csvs(season_id)
            self._mark_done(season_id, "write_csvs")
        else:
            log.info("Skipping CSV export (already done)")

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
        energy_repo = PlayerEnergyRepository(self.conn, self.league_id)
        inj_repo = InjuryRepository(self.conn, self.league_id)

        if self.league_id:
            players = self.player_repo.get_players_by_league(self.league_id)
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
                injuries = inj_repo.count_player_injuries(player.id, season_id)

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

        log.info("Aged %s players", len(players))

    def _retire(self, rng: random.Random) -> None:
        """Evaluate all players for retirement.
        Scoped to players on teams in this league's season only."""

        ret_repo = RetirementRepository(self.conn)
        inj_repo = InjuryRepository(self.conn, self.league_id)
        stats_repo = PlayerSeasonStatsRepository(self.conn)
        season_id = self._current_season_id

        max_games = stats_repo.get_max_games_played(season_id) if season_id else 162

        if self.league_id:
            players = self.player_repo.get_players_by_league(self.league_id)
        else:
            players = self.player_repo.get_all_players()
        retired = []

        for player in players:
            current_status = self.player_status_repo.get_status(player.id)
            is_unrostered = current_status in ("prospect", "unassigned", "free_agent")

            season_stats = (
                stats_repo.get_player_season(player.id, season_id)
                if season_id
                else None
            )
            games_played = 0
            if season_stats:
                games_played = max(
                    season_stats.get("bat_games_played") or 0,
                    season_stats.get("pitch_games_played") or 0,
                )

            injuries = (
                inj_repo.count_player_injuries(player.id, season_id) if season_id else 0
            )
            games_missed = (
                inj_repo.get_days_missed_in_season(player.id, season_id)
                if season_id
                else 0
            )

            status = self._should_retire(
                player.age,
                player.skills,
                is_unrostered,
                rng,
                games_played=games_played,
                games_missed=games_missed,
                season_injuries=injuries,
                max_games=max_games,
            )
            if status in ["retired", "free_agent"]:
                self.player_status_repo.set_status(player.id, status)
                row = self.team_repo.get_players_team_from_team_players(player.id)
                former_team_id = row["team_id"] if row else None
                if former_team_id:
                    self.team_repo.remove_player(former_team_id, player.id)
                if status == "retired":
                    if self.league_id:
                        ret_repo.retire_player(
                            player.id,
                            self.league_id,
                            self._current_season_id,
                            former_team_id,
                        )
                    retired.append(player)

        self.conn.commit()

        if retired:
            if self.league_id:
                out_dir = Path(TEAM_FILES_DIR) / self.league_id / str(self.year)
            else:
                out_dir = Path(TEAM_FILES_DIR) / str(self.year)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / "retired.csv"
            rows = [p.to_csv_dict() for p in retired]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            log.info("Retired %s players → %s", len(retired), path)
        else:
            log.info("Retired 0 players")

    def _write_csvs(self, season_id: str) -> None:
        """Write post-aging CSVs for teams in this league only."""
        # Scope to this league via league_season_teams
        if self.league_id:
            teams = self.team_repo.get_team_id_and_csv(season_id, self.league_id)
            out_dir = Path(TEAM_FILES_DIR) / self.league_id / str(self.year)
        else:
            raise RuntimeError("No league id to write CSVs for")
            # This is now a runtime error

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
                log.info("Skipping %s (already exists)", path)
                continue

            rows = [p.to_csv_dict() for p in players]
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            log.info("Wrote %s", path)

    def _mark_done(self, season_id: str, step: str) -> None:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        self.os_repo.mark_done(season_id, step, now)
        self.conn.commit()

    def _playoffs_complete(self, season_id: str) -> bool:
        series_repo = SeriesRepository(self.conn)
        finals = series_repo.get_finals_id(season_id)
        if finals is None:
            return False
        win_total = series_repo.get_champ(finals["id"])
        return win_total is not None and win_total["wins"] >= 4

    def _reset_player_energy(self) -> None:
        repo = PlayerEnergyRepository(self.conn, self.league_id)
        count = repo.clear_season()
        log.info("Cleared player energy for %s players", count)

    def _clear_stale_prospects(self) -> None:
        """
        Clear undrafted prospects who are too old to realistically be drafted.
        Prospects aged 24+ who are still in the pool get marked free_agent
        so they don't accumulate indefinitely across seasons.
        """
        cleared = self.player_repo.clear_stale_prospects(self.league_id)
        if cleared:
            self.conn.commit()
        log.info("Cleared %s stale prospects (age >= 24)", cleared)

    def _reset_pitcher_state(self, season_id: str) -> None:
        repo = PitcherStateRepository(self.conn, self.league_id)
        count = repo.clear_all_pitcher_state()
        log.info("Cleared pitcher state for %s pitchers", count)
        self._reset_rotation_pointers(season_id)

    def _rebuild_rotations(self, season_id: str) -> None:
        """Rebuild rotations and bullpen roles for AI teams only at the start of a new season."""
        gm_repo = GMRepository(self.conn)
        human_team_ids = gm_repo.get_human_team_ids(self.league_id or "")
        all_teams = self.team_repo.get_teams_by_season(season_id)
        ai_team_ids = {t.id for t in all_teams} - human_team_ids
        seeded = seed_ai_rotations(
            self.conn,
            season_id,
            ai_team_ids,
            statuses=["26man"],
            effective_date=f"{self.year}-04-01",
            league_id=self.league_id,
        )
        self.conn.commit()
        log.info("Rebuilt rotations and bullpen roles for %s AI teams", seeded)

    def _reset_rotation_pointers(self, season_id: str) -> None:
        rot_repo = TeamRotationsRepository(self.conn, self.league_id)
        reset = rot_repo.reset_rotation_pointers(season_id)
        self.conn.commit()
        log.info("Reset rotation pointers to sp1 for %s teams", reset)

    def _generate_draft(self, season_id: str) -> None:
        generator = DraftGenerator(self.conn, self.rng)
        total = generator.run(self.year, league_id=self.league_id)
        log.info("Draft pool ready: %s draftable players", total)

    def _write_draft_order(self, league_id: str, draft_order: list[dict]) -> None:
        """Persist the draft order and pick rights for this draft."""

        # The draft record belongs to the NEW season (created by offseason_service),
        # not the completed season. Find the newest pending draft.
        row = self.draft_repo.get_current_for_league(league_id)
        if not row:
            log.warning("no draft record found, skipping draft_order write")
            return

        ordered_ids = [e["team_id"] for e in draft_order]
        write_draft_order(self.conn, row["id"], league_id, self.year, ordered_ids)
        log.info("Draft order stored: %s teams", len(draft_order))

    def _run_draft(self, season_id: str, league_id: str) -> None:
        snake = SnakeDraft(self.conn, league_id, self.rng)
        # Build order first so we can persist it before the draft runs
        draft_order = snake._build_draft_order(season_id)
        self._write_draft_order(league_id, draft_order)
        picks = snake.run_snake_draft_with_order(draft_order, self.year, league_id)
        log.info("Draft complete: %s total picks", len(picks))

    def _trim_rosters(self, season_id: str) -> None:
        trimmer = RosterTrimmer(self.conn)
        trimmer.run(season_id)

    @staticmethod
    def _should_retire(
        age: int,
        skills: PlayerSkills,
        is_unrostered: bool,
        rng: random.Random,
        *,
        games_played: int = 0,
        games_missed: int = 0,
        season_injuries: int = 0,
        max_games: int = SEASON_LENGTH,
    ) -> str | None:
        """
        Determine if a player should retire.

        Args:
            age: Age of the player
            skills: A dict like class of skills of the player
            is_unrostered: A boolean representing whether the player is rostered
            rng: A random number generator
            games_played: The number of glames played by the player last season
            games_missed: The number of games missed due to injury
            max_games: the total season length

        Returns:
            Either a string in ('free_agent', 'retired')
            or None in the case of do not retire.
        """
        if is_unrostered:
            if age < 18:
                return None
            # Young players who actually played last season are active prospects — give
            # them a pass until they've aged out more meaningfully.
            if age < 23 and games_played > 0:
                return None
            probability = min(0.95, (age - 22) * 0.20)
        else:
            if age < 30:
                return None
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
                best = max(
                    skill_dict.get(k, 0)
                    for k in ["strikes", "stamina", "recovery", "ground_balls"]
                )
                if best >= 75:
                    return None
            else:
                best = max(skill_dict.get(k, 0) for k in ["power", "speed", "arm"])
                if best >= 72:
                    return None
            relevant_keys = pitching_skills if is_pitcher else batting_skills
            relevant = {k: v for k, v in skill_dict.items() if k in relevant_keys}
            skill_avg = sum(relevant.values()) / len(relevant)
            if age < 35:
                base = (age - 30) * 0.03
            else:
                base = 0.15 + (age - 35) * 0.09
            decline_factor = max(0.0, (50 - skill_avg) / 100)

            # Injury burden: each additional injury in the season pushes probability up.
            # Capped so a single injury year can add at most ~0.12.
            injury_factor = min(0.12, season_injuries * 0.04)

            # Availability penalty: missing more than half the season signals a body
            # breaking down. Only meaningful for players 33+.
            availability_factor = 0.0
            if age >= 33 and max_games > 0:
                missed_fraction = games_missed / max_games
                if missed_fraction > 0.5:
                    availability_factor = 0.10

            probability = min(
                0.95, base + decline_factor + injury_factor + availability_factor
            )

        if rng.random() < probability:
            if age < 30:
                return "free_agent"
            else:
                return "retired"


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument("--season-id", "-i", required=True)
    p.add_argument("--league-id", "-l", default=None)
    p.add_argument("--seed", "-s", type=int)
    return p.parse_args()


def main():
    args = get_args()
    conn = get_connection()

    configure_app_logging()
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
