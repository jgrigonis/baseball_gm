#!/usr/bin/env python3
# scripts/cligr.py
"""
CLI Game Runner — consolidates new_league.sh, run_season.sh, and clear scripts.

Usage examples:

  # Clear operations (can be combined)
  python cligr.py clear --logs
  python cligr.py clear --temp
  python cligr.py clear --db               # drops and recreates the Postgres DB
  python cligr.py clear --teams            # interactive league picker
  python cligr.py clear --teams --league-id LEAGUE_ID
  python cligr.py clear --all-teams        # ⚠ destroys all team files
  python cligr.py clear --logs --temp      # combine as needed

  # Delete every league but keep user accounts (asks first; --yes skips that)
  python cligr.py reset-leagues
  python cligr.py reset-leagues --yes

  # Make a user an admin (creates the account if it doesn't exist, asking
  # for a password); --reset-password also sets a new password
  python cligr.py make-admin USERNAME
  python cligr.py make-admin USERNAME --reset-password

  # Create a new league (no games run)
  python cligr.py new-league
  python cligr.py new-league --year 2030 --seed 42
  python cligr.py new-league --clear-db         # destroy the entire DB

  # Create a new league and immediately run seasons
  python cligr.py new-league --year 2030 --run-season
  python cligr.py new-league --year 2030 --run-season --num-years 15 --reports

  # Run the next season(s) for an existing league
  python cligr.py run-season
  python cligr.py run-season --num-years 5 --seed 99
  python cligr.py run-season --logs --game-logs --reports
  python cligr.py run-season --league-id LEAGUE_ID

Common options (all subcommands):
  Database is configured via the DATABASE_URL environment variable.
"""

import argparse
import contextlib
import datetime
import getpass
import io
import logging
import os
import random
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from scripts.create_more_seasons import create_manifests
from src.db.connection import get_connection
from src.db.init import init_db
from src.db.locks import LeagueBusy, league_lock
from src.api.services import admin as admin_service
from src.api.services.passwords import password_error, username_error
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.db.repositories.user_repo import UserRepository

from src.league.bootstrap import LeagueBootstrapper
from src.league.manifest_helper import (
    load_manifest,
    validate_manifest_structure,
    validate_manifest_uniqueness,
    find_missing_team_files,
    create_team_files,
)
from src.league.offseason.build_season_stats import build_season
from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.play_season import play_game
from src.league.rotation_seeder import seed_ai_rotations
from src.league.playoffs.play_playoffs import (
    play_series,
    generate_round_games,
    original_seed,
    _HOME_MAP_BO7,
    _SEMI_18_45_OFFSETS,
    _SEMI_27_36_OFFSETS,
    _FINAL_OFFSETS,
)
from src.league.playoffs.setup_playoffs import (
    get_top_N,
    build_bracket,
    demote_extra_starters,
)
from src.league.schedule import ScheduleGenerator, save_schedule_to_db
from src.league.statistics.league_leaders import (
    fetch_leaders,
    display as display_leaders,
)
from src.league.statistics.league_totals import (
    fetch_totals,
    display as display_totals,
)
from src.league.statistics.view_leaderboards import (
    show_all_leaderboards,
    calculate_min_pa,
)
from src.stats.loader import StatsLoader
from src.util.locations import MANIFEST_FILES_DIR, TEAM_FILES_DIR, TEMP_FILES, LOG_FILES
from src.util.logger import setup_logger

# Database is configured via DATABASE_URL environment variable
DEFAULT_YEAR = 2025
NUM_YEARS = 50  # The maximum number of years to expect manifest files for


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cligr",
        description="Baseball GM simulation CLI runner",
        epilog="Run `python cligr.py COMMAND --help` for help on a specific command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── clear ──────────────────────────────────────────────────────────────────
    clear = sub.add_parser(
        "clear",
        help="Clear logs, temp files, DB, or team files",
        description="Clear one or more resources. Multiple flags can be combined.",
    )
    clear.add_argument(
        "--logs",
        action="store_true",
        help="Delete all log files in logs/",
    )
    clear.add_argument(
        "--temp",
        action="store_true",
        help=f"Delete all files in {TEMP_FILES}/",
    )
    clear.add_argument(
        "--db",
        dest="clear_db",
        action="store_true",
        help="Drop and recreate the Postgres database (uses DATABASE_URL)",
    )
    clear.add_argument(
        "--teams",
        action="store_true",
        help="Delete team files for a league (use --league-id or pick interactively)",
    )
    clear.add_argument(
        "--league-id",
        "-l",
        help="League ID for --teams (omit for interactive picker)",
    )
    clear.add_argument(
        "--all-teams",
        action="store_true",
        help="⚠ Delete ALL team files for ALL leagues (destructive)",
    )

    # ── reset-leagues ──────────────────────────────────────────────────────────
    reset = sub.add_parser(
        "reset-leagues",
        help="Delete every league but keep user accounts",
        description=(
            "Delete every league with everything it owns, plus its team_files "
            "folder, the same way the last GM leaving a league does. User "
            "accounts stay, so nobody has to sign up again."
        ),
    )
    reset.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the confirmation prompt",
    )

    # ── make-admin ─────────────────────────────────────────────────────────────
    make_admin = sub.add_parser(
        "make-admin",
        help="Give a user admin access, creating the account if needed",
        description=(
            "Give USERNAME access to the admin pages (/admin/). If there's no "
            "such account, it is created and you're asked for its password. "
            "Use it to get back in if the admin login is lost."
        ),
    )
    make_admin.add_argument("username", help="The login name")
    make_admin.add_argument(
        "--reset-password",
        action="store_true",
        help="Also ask for a new password for an existing account",
    )

    # ── new-league ─────────────────────────────────────────────────────────────
    new = sub.add_parser(
        "new-league",
        help="Create a fresh league (optionally run seasons immediately)",
        description="Bootstraps a new league. Add --run-season to simulate seasons right away.",
    )
    new.add_argument(
        "--year",
        "-y",
        type=int,
        default=DEFAULT_YEAR,
        help=f"Starting season year (default: {DEFAULT_YEAR})",
    )
    new.add_argument(
        "--manifest",
        "-m",
        default="world_league",
        help="Manifest file prefix (default: world_league)",
    )
    new.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    new.add_argument(
        "--run-season",
        action="store_true",
        help="Run season(s) immediately after creating the league",
    )
    new.add_argument(
        "--num-years",
        "-n",
        type=int,
        default=1,
        help="Number of seasons to simulate (requires --run-season, default: 1)",
    )
    new.add_argument(
        "--game-logs",
        action="store_true",
        help="Write per-game log files — requires --run-season (verbose, slow)",
    )
    new.add_argument(
        "--reports",
        action="store_true",
        help="Generate leaderboard and totals reports — requires --run-season",
    )
    new.add_argument(
        "--logs",
        action="store_true",
        help="Write season-level log files — requires --run-season",
    )
    new.add_argument(
        "--clear-db",
        action="store_true",
        help="Destroy the DB",
    )
    new.add_argument(
        "--clear-logs",
        action="store_true",
        help="Clear logs before starting",
    )
    new.add_argument(
        "--clear-temp",
        action="store_true",
        help="Clear temp files before starting",
    )

    # ── run-season ─────────────────────────────────────────────────────────────
    run = sub.add_parser(
        "run-season",
        help="Run the next season(s) for an existing league",
        description="Continues from wherever the league left off. Year is auto-detected.",
    )
    run.add_argument(
        "--num-years",
        "-n",
        type=int,
        default=1,
        help="Number of seasons to simulate (default: 1)",
    )
    run.add_argument(
        "--league-id",
        "-l",
        help="League ID (default: auto-detect from DB)",
    )
    run.add_argument(
        "--seed",
        "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    run.add_argument(
        "--logs",
        action="store_true",
        help="Write season-level log files",
    )
    run.add_argument(
        "--game-logs",
        action="store_true",
        help="Write per-game log files (verbose, slow)",
    )
    run.add_argument(
        "--reports",
        action="store_true",
        help="Generate leaderboard and totals reports after each season",
    )

    # ── reports ────────────────────────────────────────────────────────────────
    rpt = sub.add_parser(
        "reports",
        help="Generate leaderboard and stats reports for a season",
        description="Run leaderboards, league totals, and league leaders for a given year.",
    )
    rpt.add_argument(
        "--year",
        "-y",
        type=int,
        default=None,
        help="Single season year to report on",
    )
    rpt.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Start year for a range of seasons",
    )
    rpt.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="End year for a range of seasons",
    )
    rpt.add_argument(
        "--league-id",
        "-l",
        help="League ID (default: auto-detect from DB)",
    )
    rpt.add_argument(
        "--logs",
        action="store_true",
        help="Write output to log files",
    )

    return parser


# ── Directory helpers ──────────────────────────────────────────────────────────


def _logs_dir() -> Path:
    return LOG_FILES


def _temp_dir() -> Path:
    return TEMP_FILES


def _team_files_dir() -> Path:
    return TEAM_FILES_DIR


# ── Clear helpers ───────────────────────────────────────────────────────────────


def clear_logs() -> None:
    d = _logs_dir()
    if not d.exists():
        print("  logs/: nothing to clear")
        return
    removed = 0
    for f in d.glob("*.log"):
        f.unlink()
        removed += 1
    print(f"  logs/: removed {removed} log file(s)")


def clear_temp() -> None:
    d = _temp_dir()
    if not d.exists():
        print(f"  {TEMP_FILES}/: nothing to clear")
        return
    removed = 0
    for f in d.iterdir():
        if f.is_file():
            f.unlink()
            removed += 1
        elif f.is_dir():
            shutil.rmtree(f)
            removed += 1
    print(f"  {TEMP_FILES}/: removed {removed} item(s)")


def clear_db() -> None:
    """
    Drop and recreate the Postgres database.
    Reads DATABASE_URL from environment to find the DB name.
    """
    url = os.environ.get("DATABASE_URL", "")
    # Extract db name from URL: postgresql://user@host/dbname
    db_name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] if "/" in url else None
    if not db_name:
        print("  ❌ Could not determine DB name from DATABASE_URL")
        return
    try:
        subprocess.run(["dropdb", "--if-exists", db_name], check=True)
        subprocess.run(["createdb", db_name], check=True)
        print(f"  Dropped and recreated database: {db_name}")
    except subprocess.CalledProcessError as e:
        print(f"  ❌ DB reset failed: {e}")
    except FileNotFoundError:
        print("  ❌ dropdb/createdb not found — reset the database manually")


def clear_all_teams() -> None:
    d = _team_files_dir()
    if not d.exists():
        print(f"  {TEAM_FILES_DIR}/: nothing to clear")
        return
    shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    print(f"  {TEAM_FILES_DIR}/: cleared all team files")


def clear_teams_for_league(league_id: str) -> None:
    """Delete the league's team files directory."""
    league_dir = _team_files_dir() / league_id
    if not league_dir.exists():
        print(f"  No team files found for league {league_id}")
        return
    shutil.rmtree(league_dir)
    print(f"  Deleted {league_dir}")


def delete_league(conn, league_id: str) -> None:
    """Delete a league with everything it owns, then its team files."""
    # Not while a sim is running for it.
    with league_lock(conn, league_id):
        LeagueRepository(conn).delete(league_id)
        conn.commit()
    # The team and draft-class CSVs the league was built from.
    shutil.rmtree(_team_files_dir() / league_id, ignore_errors=True)


def pick_league_interactively() -> str | None:
    """Show a numbered list of leagues from the DB and return the chosen league_id."""
    try:
        conn = get_connection()
        rows = LeagueRepository(conn).list_all()
    except Exception as e:
        print(f"  Could not read leagues: {e}")
        return None

    if not rows:
        print("  No leagues found in database")
        return None

    print("\n  Leagues:")
    for i, row in enumerate(rows, 1):
        print(f"    {i}. {row['name']} ({row['state']})  [{row['id']}]")

    try:
        choice = input("\n  Pick a league number (or q to quit): ").strip()
        if choice.lower() == "q":
            return None
        idx = int(choice) - 1
        if not (0 <= idx < len(rows)):
            print("  Invalid choice")
            return None
        return rows[idx]["id"]
    except ValueError, KeyboardInterrupt:
        print("\n  Cancelled")
        return None


# ── Season helpers ──────────────────────────────────────────────────────────────


def _bootstrap_first_season(
    year: int | None, manifest_filename: str | None, seed: int | None
):
    """
    Create a fresh league, and return
    (conn, league_id, season_id, team_ids).

    Order matters:
      1. Create the league record first to get league_id
      2. Create team CSV files scoped to {year}/{league_id}/
      3. Bootstrap from manifest with the known league_id
         so bootstrap_from_manifest finds files in the right place
    """
    conn = get_connection()
    init_db(conn)

    if year is None:
        year = "2025"

    if manifest_filename is None:
        manifest_filename = "world_league"

    margs = argparse.Namespace(
        file=manifest_filename, year=year, number=NUM_YEARS, overwrite=False
    )
    create_manifests(margs)

    rng = random.Random(seed)
    manifest_path = Path(MANIFEST_FILES_DIR) / f"{manifest_filename}-{year}.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = load_manifest(str(manifest_path))
    validate_manifest_structure(manifest)
    validate_manifest_uniqueness(manifest)

    # 1. Create the league record first so we have league_id for file paths
    league_id = str(uuid.UUID(int=rng.getrandbits(128)).hex)
    league_repo = LeagueRepository(conn)
    league_id = league_repo.get_or_create_by_name(manifest["league_name"], league_id)
    conn.commit()  # moved from league_repo might need to move down...

    # 2. Create team CSV files in the right location: {year}/{league_id}/
    missing = find_missing_team_files(manifest, league_id=league_id)
    if missing:
        print(f"  Generating {len(missing)} missing team CSV files...")
        create_team_files(missing, year, rng=rng, league_id=league_id)

    start_date_str = manifest.get("season_start_date", f"{year}-04-01")
    start_date = datetime.date.fromisoformat(start_date_str)

    # 3. Bootstrap with known league_id — finds files in {year}/{league_id}/
    boot = LeagueBootstrapper(conn, rng=rng)
    league_id, teams, season_id = boot.bootstrap_from_manifest(
        manifest,
        start_date,
        league_id=league_id,
        force_new_teams=True,
    )
    game_repo = GameRepository(conn)
    existing_games = game_repo.games_remaining(season_id)
    if existing_games == 0:
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=season_id,
            team_ids=[t.id for t in teams],
            start_date=start_date,
            games_per_series=3,
            home_and_away=True,
        )
        save_schedule_to_db(conn, schedule)
        print(f"  Schedule: {len(schedule)} games")

    print(f"  League: {league_id}")
    print(f"  Season: {season_id}")
    print(f"  Teams:  {len(teams)}")
    return conn, league_id, season_id, [t.id for t in teams]


def _create_next_season_cli(
    conn, league_id: str, current_season_id: str, next_year: int
):
    """
    Create the next season record directly in DB (same teams, new schedule).
    Returns (new_season_id, team_ids).
    """
    sr = SeasonRepository(conn)
    lr = LeagueRepository(conn)

    current = sr.get_season(current_season_id)
    current_name = current["name"] if current else f"Season {next_year - 1}"
    parts = current_name.rsplit(" ", 1)
    try:
        new_name = f"{parts[0]} {int(parts[1]) + 1}"
    except IndexError, ValueError:
        new_name = f"Season {next_year}"

    # Check if already exists
    existing = sr.get_by_league_and_year(league_id, next_year)
    if existing:
        season_id = existing["id"]
        team_ids = lr.get_league_teams(league_id, season_id)
        print(f"  Season {next_year} already exists")
        return season_id, team_ids

    season_id = sr.create_season(next_year, new_name)
    lr.assign_season_to_league(league_id, season_id)

    team_ids = lr.get_league_teams(league_id, current_season_id)
    for tid in team_ids:
        lr.assign_team_to_league(league_id, season_id, tid)

    start_date = datetime.date(next_year, 4, 1)
    rng = random.Random()
    scheduler = ScheduleGenerator(rng=rng)
    schedule = scheduler.create_schedule(
        season_id=season_id,
        team_ids=team_ids,
        start_date=start_date,
        games_per_series=3,
        home_and_away=True,
    )
    save_schedule_to_db(conn, schedule)

    # Seed rotations for all teams (CLI = all-AI, no human GMs)
    seeded = seed_ai_rotations(
        conn,
        season_id,
        set(team_ids),
        statuses=["26man"],
        effective_date=start_date.isoformat(),
        league_id=league_id,
    )
    print(f"  Rotations seeded for {seeded} teams")

    conn.commit()
    print(f"  Created season {next_year}: {len(schedule)} games scheduled")
    return season_id, team_ids


def _play_regular_season(
    conn, season_id: str, league_id: str, seed: int | None, game_logs: bool
):
    """Play all incomplete regular season games."""

    lr = LeagueRepository(conn)
    league_mode = lr.get_league_mode(league_id)

    # Seed rotations for all teams if not already set (idempotent).
    # Covers the first season of a new league and any run-season resume.
    team_ids = lr.get_league_teams(league_id, season_id)
    season_start = datetime.date(
        SeasonRepository(conn).get_year(season_id)["year"], 4, 1
    )
    seeded = seed_ai_rotations(
        conn,
        season_id,
        set(team_ids),
        statuses=["26man"],
        effective_date=season_start.isoformat(),
        league_id=league_id,
    )
    if seeded:
        conn.commit()
        print(f"  Seeded rotations for {seeded} teams")

    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn, league_id)

    games = game_repo.get_season_games(
        season_id=season_id, incomplete_only=True, regular_season_only=True
    )
    if not games:
        print("  No incomplete regular season games found")
        return

    rng = random.Random(seed)
    args = argparse.Namespace(logs=game_logs)
    completed = 0
    errors = 0

    print(f"  Playing {len(games)} regular season games...")
    for i, game_info in enumerate(games, 1):
        game_dict = dict(game_info)
        try:
            play_game(
                conn=conn,
                args=args,
                team_repo=team_repo,
                game_repo=game_repo,
                team_game_repo=team_game_repo,
                rotations_repo=rotations_repo,
                season_id=season_id,
                game_info=game_dict,
                rng=rng,
                league_id=league_id,
                league_mode=league_mode,
            )
            completed += 1
            try:
                conn.rollback()
            except Exception:
                pass
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            errors += 1
            print(f"    ❌ Game {game_dict['game_id']} failed: {e}")

        if i % 100 == 0:
            print(f"    {i}/{len(games)} games complete ({errors} errors)")

    # Final stats rollup
    try:
        n = build_season(conn, season_id)
        print(f"  Stats rollup: {n} rows")
    except Exception as e:
        print(f"  Stats rollup failed (non-fatal): {e}")

    print(f"  Regular season complete: {completed} played, {errors} errors")


def _setup_playoffs(conn, season_id: str, year: int, league_id: str):
    """Seed top 8, build bracket, demote extra starters."""
    if PlayoffRepository(conn).existing_series_exist(season_id):
        print("  Playoff bracket already set up")
        return

    seeds = get_top_N(conn, season_id)
    last_game = GameRepository(conn).last_game_date(season_id)
    playoff_start = (
        datetime.date.fromisoformat(last_game["d"]) + datetime.timedelta(days=5)
        if last_game
        else datetime.date(year, 10, 1)
    )
    demote_extra_starters(conn, season_id, seeds, keep=4, league_id=league_id)
    build_bracket(conn, season_id, seeds, playoff_start)
    conn.commit()
    print(f"  Playoff bracket ready. Start date: {playoff_start}")


def _play_playoffs(
    conn, season_id: str, league_id: str, seed: int | None, game_logs: bool
):
    """Play the full playoff bracket to completion."""
    lr = LeagueRepository(conn)
    league_mode = lr.get_league_mode(league_id)
    pr = PlayoffRepository(conn)

    rng = random.Random(seed)
    args = argparse.Namespace(logs=game_logs, season_id=season_id)

    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn, league_id)

    seeds = pr.get_seeds(season_id)

    first_game = pr.get_first_game(season_id)
    playoff_start = datetime.date.fromisoformat(first_game["game_date"])

    print("  Playing Round 1...")
    r1_winners = {}
    for name, hi, lo in [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]:
        sid = pr.get_series_id(season_id, name)
        winner = play_series(
            conn,
            args,
            team_repo,
            game_repo,
            team_game_repo,
            rotations_repo,
            sid,
            name,
            best_of=5,
            rng=rng,
            league_id=league_id,
            league_mode=league_mode,
        )
        r1_winners[name] = winner

    print("  Playing Semifinals...")
    semi_winners = []
    for name, team_a, team_b in [
        ("[1,8]v[4,5]", r1_winners["1v8"], r1_winners["4v5"]),
        ("[2,7]v[3,6]", r1_winners["2v7"], r1_winners["3v6"]),
    ]:
        sid = pr.get_series_id(season_id, name)
        sa, sb = original_seed(seeds, team_a), original_seed(seeds, team_b)
        high = team_a if sa < sb else team_b
        low = team_b if sa < sb else team_a
        if name == "[1,8]v[4,5]":
            _SEMI_OFFSETS = _SEMI_18_45_OFFSETS
        else:
            _SEMI_OFFSETS = _SEMI_27_36_OFFSETS
        generate_round_games(
            conn, season_id, sid, high, low, _HOME_MAP_BO7, playoff_start, _SEMI_OFFSETS
        )
        winner = play_series(
            conn,
            args,
            team_repo,
            game_repo,
            team_game_repo,
            rotations_repo,
            sid,
            name,
            best_of=7,
            rng=rng,
            league_id=league_id,
            league_mode=league_mode,
        )
        semi_winners.append((winner, original_seed(seeds, winner)))

    print("  Playing Finals...")
    fa, sa = semi_winners[0]
    fb, sb = semi_winners[1]
    high = fa if sa < sb else fb
    low = fb if sa < sb else fa
    finals_id = pr.get_series_id(season_id, "Finals")
    generate_round_games(
        conn,
        season_id,
        finals_id,
        high,
        low,
        _HOME_MAP_BO7,
        playoff_start,
        _FINAL_OFFSETS,
    )
    champion = play_series(
        conn,
        args,
        team_repo,
        game_repo,
        team_game_repo,
        rotations_repo,
        finals_id,
        "Finals",
        best_of=7,
        rng=rng,
        league_id=league_id,
        league_mode=league_mode,
    )

    champ_name = TeamRepository(conn).get_name(champion)
    print(f"  🏆 Champion: {champ_name}")


def _run_offseason_pipeline(conn, season_id: str, league_id: str, seed: int | None):
    """Run the full offseason pipeline (AI snake draft runs for all teams)."""
    rng = random.Random(seed)
    pipeline = OffseasonPipeline(conn, rng)
    # CLI mode: let run_draft execute (all-AI snake draft — do NOT pre-mark done)
    pipeline.run(season_id, league_id=league_id)


def _make_logger(name: str, enabled: bool):
    """Return a logger if enabled, else None."""
    if not enabled:
        return None
    return setup_logger(
        name=name,
        level=logging.INFO,
        console_level=logging.WARNING,
        log_id=name,
        log_to_file=True,
    )


def _run_reports(season_id: str, logs: bool = False):
    """Run leaderboard and stats reports by importing directly."""
    conn = get_connection()

    # --- Season label for display ---
    row = SeasonRepository(conn).get_season(season_id)
    season_label = f"{row['name']} ({row['year']})" if row else season_id[:8]

    # --- Leaderboards (view_leaderboards) ---
    print("  Leaderboards...")
    try:
        logger = _make_logger("view_leaderboards", logs)

        min_pa, min_ip = calculate_min_pa(season_id, logger=logger)

        with StatsLoader() as loader:
            all_players = loader.load_season_players_with_stats(season_id)
        show_all_leaderboards(all_players, min_pa=min_pa, min_ip=min_ip, logger=logger)
    except Exception as e:
        print(f"  ⚠️  Leaderboards failed: {e}")

    # --- League Totals ---
    print("  League Totals...")
    try:
        logger = _make_logger("league_totals", logs)
        totals = fetch_totals(conn, season_id)
        display_totals(totals, season_label, logger=logger)
    except Exception as e:
        print(f"  ⚠️  League Totals failed: {e}")

    # --- League Leaders ---
    print("  League Leaders...")
    try:
        logger = _make_logger("league_leaders", logs)
        with StatsLoader() as loader:
            all_players = loader.load_season_players_with_stats(season_id)
        leaders = fetch_leaders(all_players, min_pa=min_pa, min_ip=min_ip)
        display_leaders(leaders, season_label, logger=logger)
    except Exception as e:
        print(f"  ⚠️  League Leaders failed: {e}")

    conn.close()


def _run_one_season(conn, season_id: str, league_id: str, year: int, args) -> None:
    """Play one complete season: regular season → reports → playoffs → offseason."""
    print(f"\n{'=' * 60}")
    print(f"  Season {year}  (season_id={season_id[:8]}...)")
    print(f"{'=' * 60}")

    _play_regular_season(conn, season_id, league_id, args.seed, args.game_logs)

    if args.reports:
        print("  Generating reports...")
        _run_reports(season_id, logs=args.logs)

    print("  Setting up playoffs...")
    _setup_playoffs(conn, season_id, year, league_id)

    print("  Playing playoffs...")
    _play_playoffs(conn, season_id, league_id, args.seed, args.game_logs)

    print("  Running offseason pipeline...")
    _run_offseason_pipeline(conn, season_id, league_id, args.seed)


# ── Command handlers (new-league, run-season) ───────────────────────────────────


def cmd_new_league(args) -> None:
    if args.clear_db:
        msg = "⚠️  This will destroy the entire database. Continue? [y/N] "
        if input(msg).strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return
        clear_db()

    if args.clear_logs:
        clear_logs()
    if args.clear_temp:
        clear_temp()

    print(f"\n🏟️  Creating new league — Year {args.year}")
    conn, league_id, season_id, _ = _bootstrap_first_season(
        args.year, args.manifest, args.seed
    )
    print("\n✅ League created.")

    if args.run_season:
        current_season_id = season_id
        for n in range(args.num_years):
            year = args.year + n
            if n > 0:
                current_season_id, _ = _create_next_season_cli(
                    conn, league_id, current_season_id, year
                )
            _run_one_season(conn, current_season_id, league_id, year, args)
        print(f"\n✅ Done — {args.num_years} season(s) complete.")


def cmd_run_season(args) -> None:
    conn = get_connection()

    # Resolve league
    league_id = args.league_id
    if not league_id:
        rows = LeagueRepository(conn).list_all()
        if not rows:
            print("❌ No leagues found in DB.")
            sys.exit(1)
        if len(rows) == 1:
            league_id = rows[0]["id"]
            print(f"  Using league: {rows[0]['name']} ({league_id[:8]}...)")
        else:
            league_id = pick_league_interactively()
            if not league_id:
                sys.exit(0)

    sr = SeasonRepository(conn)
    pr = PlayoffRepository(conn)

    seasons = sr.get_seasons_for_league(league_id)
    if not seasons:
        print("❌ No season found for this league.")
        sys.exit(1)

    last = seasons[0]
    current_season_id = last["id"]
    current_year = last["year"]

    if pr.has_champion(current_season_id):
        next_year = current_year + 1
        print(f"  Season {current_year} complete. Creating season {next_year}...")
        current_season_id, _ = _create_next_season_cli(
            conn, league_id, current_season_id, next_year
        )
        current_year = next_year

    for n in range(args.num_years):
        year = current_year + n
        if year == current_year:
            season_id = current_season_id
        else:
            season_id, _ = _create_next_season_cli(
                conn, league_id, current_season_id, year
            )
            current_season_id = season_id
            current_year = year

        _run_one_season(conn, season_id, league_id, year, args)

    print(f"\n✅ Done — {args.num_years} season(s) complete.")


# ── Clear handler ──────────────────────────────────────────────────────────────


def cmd_clear(args) -> None:
    if not any([args.logs, args.temp, args.clear_db, args.teams, args.all_teams]):
        print(
            "Nothing to clear — specify at least one of: "
            "--logs, --temp, --db, --teams, --all-teams"
        )
        return

    if args.all_teams:
        confirm = input("⚠️  Delete ALL team files for ALL leagues? [y/N] ").strip()
        if confirm.lower() not in ("y", "yes"):
            print("  Aborted")
            return
        clear_all_teams()

    if args.teams and not args.all_teams:
        league_id = args.league_id or pick_league_interactively()
        if league_id:
            clear_teams_for_league(league_id)

    if args.clear_db:
        confirm = input("⚠️  Reset the Postgres database? [y/N] ").strip()
        if confirm.lower() not in ("y", "yes"):
            print("  Aborted")
        else:
            clear_db()

    if args.logs:
        clear_logs()

    if args.temp:
        clear_temp()


# ── Reset leagues handler ──────────────────────────────────────────────────────


def cmd_reset_leagues(args) -> None:
    conn = get_connection()
    init_db(conn)

    leagues = LeagueRepository(conn).list_all()
    if not leagues:
        print("No leagues to delete.")
        return

    print(f"This deletes all {len(leagues)} league(s) and their team files:")
    for league in leagues:
        print(f"  {league['name']} ({league['state']})  [{league['id']}]")
    print("User accounts are kept.")

    if not args.yes:
        confirm = input("⚠️  Delete these leagues? [y/N] ").strip()
        if confirm.lower() not in ("y", "yes"):
            print("  Aborted")
            return

    for league in leagues:
        try:
            delete_league(conn, league["id"])
        except LeagueBusy:
            print(f"  ❌ A sim is running for {league['name']}, stop it and try again")
            sys.exit(1)
        print(f"  Deleted {league['name']}  [{league['id']}]")

    users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    print(f"\n✅ Deleted {len(leagues)} league(s), kept {users} user account(s).")


def _ask_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        error = password_error(password, getpass.getpass("Confirm password: "))
        if not error:
            return password
        print(f"  ❌ {error}")


def cmd_make_admin(args) -> None:
    conn = get_connection()
    init_db(conn)
    user_repo = UserRepository(conn)

    user = user_repo.get_by_username(args.username)
    if not user:
        error = username_error(args.username)
        if error:
            print(f"❌ {error}")
            sys.exit(1)
        print(f"No user {args.username!r} yet, creating one.")
        admin_service.create_user(
            conn, args.username, _ask_password(), None, True, must_change=False
        )
        print(f"✅ Created admin {args.username}.")
        return

    if args.reset_password:
        admin_service.set_password(conn, user["id"], _ask_password(), must_change=False)
        print(f"  New password set for {user['username']}.")
    user_repo.set_admin(user["id"], True)
    conn.commit()
    print(f"✅ {user['username']} is an admin.")


def _resolve_league(conn, league_id_arg):
    """Return league_id, prompting if needed."""
    if league_id_arg:
        return league_id_arg
    rows = LeagueRepository(conn).list_all()
    if not rows:
        print("❌ No leagues found in DB.")
        sys.exit(1)
    if len(rows) == 1:
        return rows[0]["id"]
    league_id = pick_league_interactively()
    if not league_id:
        sys.exit(0)
    return league_id


def cmd_reports(args) -> None:
    conn = get_connection()
    league_id = _resolve_league(conn, args.league_id)

    # Determine year range
    if args.start_year and args.end_year:
        years = list(range(args.start_year, args.end_year + 1))
    elif args.start_year or args.end_year:
        print("❌ Provide both --start-year and --end-year for a range.")
        sys.exit(1)
    elif args.year:
        years = [args.year]
    else:
        print("❌ Provide --year or --start-year/--end-year.")
        sys.exit(1)

    # Range mode: capture output to temp_files/
    range_mode = len(years) > 1
    if range_mode:
        _temp_dir().mkdir(parents=True, exist_ok=True)

    for year in years:
        row = SeasonRepository(conn).get_by_league_and_year(league_id, year)
        if not row:
            print(f"⚠️  No season found for year {year} — skipping")
            continue

        season_id = row["id"]
        print(f"\n📊 Reports for {year} (season {season_id[:8]}...)")

        if range_mode:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                _run_reports(season_id, logs=args.logs)
            output = buf.getvalue()
            print(output, end="")  # still show on screen

            # Append to per-report temp files
            # leaders_path = (
            #     _temp_dir() / f"league_leaders_{args.start_year}_{args.end_year}.txt"
            # )
            # totals_path = (
            #     _temp_dir() / f"league_totals_{args.start_year}_{args.end_year}.txt"
            # )
            # Split output at section boundaries and write to respective files
            # Simpler: write everything to a combined file, plus individual files
            combined_path = (
                _temp_dir() / f"reports_{args.start_year}_{args.end_year}.txt"
            )
            with open(combined_path, "a") as f:
                f.write(f"\n=== {year} ===\n")
                f.write(output)
        else:
            _run_reports(season_id, logs=args.logs)

    if range_mode:
        print(f"\n✅ Done — output saved to {combined_path}")
    else:
        print("\n✅ Done.")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "reports":
        cmd_reports(args)

    elif args.command == "clear":
        cmd_clear(args)

    elif args.command == "reset-leagues":
        cmd_reset_leagues(args)

    elif args.command == "make-admin":
        cmd_make_admin(args)

    elif args.command == "new-league":
        cmd_new_league(args)

    elif args.command == "run-season":
        cmd_run_season(args)


if __name__ == "__main__":
    main()
