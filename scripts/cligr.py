#!/usr/bin/env python3
# scripts/cligr.py
"""
CLI Game Runner — consolidates new_league.sh, run_season.sh, and clear scripts.

Usage examples:

  # Clear operations (can be combined)
  python cligr.py clear --logs
  python cligr.py clear --temp
  python cligr.py clear --db               # clears default DB (cli.db)
  python cligr.py clear --db myfile.db
  python cligr.py clear --teams            # interactive league picker
  python cligr.py clear --teams --league-id LEAGUE_ID
  python cligr.py clear --all-teams        # ⚠ destroys all team files
  python cligr.py clear --logs --temp      # combine as needed

  # Start a brand new league and sim it
  python cligr.py new-league
  python cligr.py new-league --year 2026 --seed 42 --num-years 3
  python cligr.py new-league --logs --game-logs --reports
  python cligr.py new-league --yes         # skip confirmation prompt

  # Run the next season for an existing league
  python cligr.py run-season
  python cligr.py run-season --year 2027 --seed 99
  python cligr.py run-season --logs --game-logs --reports
  python cligr.py run-season --league-id LEAGUE_ID

Common options (all subcommands):
  --db FILENAME       DB file to use (default: cli.db)
"""

import argparse
import shutil
import sys
from pathlib import Path

from src.db.connection import get_connection
from src.util.locations import LEAGUE_FILES_DIR, TEAM_FILES_DIR


DEFAULT_DB = "cli.db"
DEFAULT_YEAR = 2025


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cligr",
        description="Baseball GM simulation CLI runner",
    epilog="Run `python cligr.py COMMAND --help` for help on a specific command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", "-d",
        default=DEFAULT_DB,
        help=f"DB filename (default: {DEFAULT_DB})",
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
        "--logs", action="store_true",
        help="Delete all log files in logs/",
    )
    clear.add_argument(
        "--temp", action="store_true",
        help="Delete all files in temp_files/",
    )
    clear.add_argument(
        "--db", dest="clear_db", action="store_true",
        help="Delete the DB file specified by the top-level --db flag",
    )
    clear.add_argument(
        "--teams", action="store_true",
        help="Delete team files for a league (use --league-id or pick interactively)",
    )
    clear.add_argument(
        "--league-id", "-l",
        help="League ID for --teams (omit for interactive picker)",
    )
    clear.add_argument(
        "--all-teams", action="store_true",
        help="⚠ Delete ALL team files for ALL leagues (destructive)",
    )

    # ── new-league ─────────────────────────────────────────────────────────────
    new = sub.add_parser(
        "new-league",
        help="Create a fresh league and sim it",
        description="Destroys the existing DB, bootstraps a new league, and runs seasons.",
    )
    new.add_argument(
        "--year", "-y", type=int, default=DEFAULT_YEAR,
        help=f"Starting season year (default: {DEFAULT_YEAR})",
    )
    new.add_argument(
        "--num-years", "-n", type=int, default=1,
        help="Number of seasons to simulate (default: 1)",
    )
    new.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed for reproducibility",
    )
    new.add_argument(
        "--logs", action="store_true",
        help="Write season-level log files",
    )
    new.add_argument(
        "--game-logs", action="store_true",
        help="Write per-game log files (verbose, slow)",
    )
    new.add_argument(
        "--reports", action="store_true",
        help="Generate leaderboard and totals reports after each season",
    )
    new.add_argument(
        "--yes", action="store_true",
        help="Skip the destructive-action confirmation prompt",
    )
    new.add_argument(
        "--clear-db", action="store_true",
        help="Skip DB deletion confirmation prompt",
    )
    new.add_argument(
        "--clear-logs", action="store_true",
        help="Clear logs before starting",
    )
    new.add_argument(
        "--clear-temp", action="store_true",
        help="Clear temp files before starting",
    )

    # ── run-season ─────────────────────────────────────────────────────────────
    run = sub.add_parser(
        "run-season",
        help="Run the next season for an existing league",
        description="Bootstraps the next year's manifest and plays through the season.",
    )
    run.add_argument(
        "--year", "-y", type=int, default=2026,
        help="Season year to run (default: 2026)",
    )
    run.add_argument(
        "--num-years", "-n", type=int, default=1,
        help="Number of seasons to simulate (default: 1)",
    )
    run.add_argument(
        "--league-id", "-l",
        help="League ID (default: auto-detect from DB)",
    )
    run.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed for reproducibility",
    )
    run.add_argument(
        "--logs", action="store_true",
        help="Write season-level log files",
    )
    run.add_argument(
        "--game-logs", action="store_true",
        help="Write per-game log files (verbose, slow)",
    )
    run.add_argument(
        "--reports", action="store_true",
        help="Generate leaderboard and totals reports after each season",
    )

    # ── reports ────────────────────────────────────────────────────────────────
    rpt = sub.add_parser(
        "reports",
        help="Generate leaderboard and stats reports for a season",
        description="Run leaderboards, league totals, and league leaders for a given year.",
    )
    rpt.add_argument(
        "--year", "-y", type=int, default=2025,
        help="Season year to report on (default: 2025)",
    )
    rpt.add_argument(
        "--league-id", "-l",
        help="League ID (default: auto-detect from DB)",
    )
    rpt.add_argument(
        "--logs", action="store_true",
        help="Write output to log files",
    )

    return parser


# ── Directory helpers ──────────────────────────────────────────────────────────

def _project_root() -> Path:
    """Resolve the project root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def _logs_dir() -> Path:
    return _project_root() / "logs"


def _temp_dir() -> Path:
    return _project_root() / "temp_files"


def _db_path(db_filename: str) -> Path:
    """DB files live in leagues/ under the project root."""
    return Path(LEAGUE_FILES_DIR) / db_filename


def _team_files_dir() -> Path:
    return Path(TEAM_FILES_DIR)


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
        print("  temp_files/: nothing to clear")
        return
    removed = 0
    for f in d.iterdir():
        if f.is_file():
            f.unlink()
            removed += 1
        elif f.is_dir():
            shutil.rmtree(f)
            removed += 1
    print(f"  temp_files/: removed {removed} item(s)")


def clear_db(db_filename: str) -> None:
    p = _db_path(db_filename)
    if p.exists():
        p.unlink()
        print(f"  Deleted {p}")
    else:
        print(f"  {p}: not found, nothing to delete")


def clear_all_teams() -> None:
    d = _team_files_dir()
    if not d.exists():
        print("  team_files/: nothing to clear")
        return
    shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    print(f"  team_files/: cleared all team files")


def clear_teams_for_league(league_id: str) -> None:
    """Delete all year subdirectories that contain a league_id folder."""
    d = _team_files_dir()
    if not d.exists():
        print("  team_files/: nothing to clear")
        return
    removed = 0
    for year_dir in sorted(d.iterdir()):
        if not year_dir.is_dir():
            continue
        league_dir = year_dir / league_id
        if league_dir.exists():
            shutil.rmtree(league_dir)
            removed += 1
            print(f"  Deleted {league_dir}")
    if removed == 0:
        print(f"  No team files found for league {league_id}")
    else:
        print(f"  Removed {removed} year folder(s) for league {league_id}")


def pick_league_interactively(db_filename: str) -> str | None:
    """Show a numbered list of leagues from the DB and return the chosen league_id."""
    try:
        conn = get_connection(db_filename)
        rows = conn.execute(
            "SELECT id, name, state FROM leagues ORDER BY rowid"
        ).fetchall()
    except Exception as e:
        print(f"  Could not read leagues from {db_filename}: {e}")
        return None

    if not rows:
        print(f"  No leagues found in {db_filename}")
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
    except (ValueError, KeyboardInterrupt):
        print("\n  Cancelled")
        return None



# ── Season helpers ──────────────────────────────────────────────────────────────

def _get_conn(db_filename: str):
    return get_connection(db_filename)


def _bootstrap_first_season(db_filename: str, year: int, seed: int | None):
    """
    Initialise the DB, create a fresh league, and return
    (conn, league_id, season_id, team_ids).

    Order matters:
      1. Create the league record first to get league_id
      2. Create team CSV files scoped to {year}/{league_id}/
      3. Bootstrap from manifest with the known league_id
         so bootstrap_from_manifest finds files in the right place
    """
    import datetime
    import random
    from src.db.init import init_db
    from src.db.repositories.league_repo import LeagueRepository
    from src.league.bootstrap import LeagueBootstrapper
    from src.league.manifest_helper import (
        load_manifest, validate_manifest_structure, validate_manifest_uniqueness,
        find_missing_team_files, create_team_files,
    )
    from src.league.schedule import ScheduleGenerator, save_schedule_to_db
    from src.util.locations import MANIFEST_FILES_DIR

    conn = get_connection(db_filename)
    init_db(conn)

    rng = random.Random(seed)
    manifest_path = Path(MANIFEST_FILES_DIR) / f"world_league-{year}.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = load_manifest(str(manifest_path))
    validate_manifest_structure(manifest)
    validate_manifest_uniqueness(manifest)

    # 1. Create the league record first so we have league_id for file paths
    league_repo = LeagueRepository(conn)
    league_id = league_repo.create_league(manifest["league_name"])

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
        manifest, start_date, league_id=league_id
    )

    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = ?", (season_id,)
    ).fetchone()[0]
    if existing_games == 0:
        scheduler = ScheduleGenerator(rng=rng)
        schedule = scheduler.create_schedule(
            season_id=season_id,
            team_ids=[t.id for t in teams],
            start_date=start_date,
            games_per_matchup=3,
            home_and_away=True,
        )
        save_schedule_to_db(conn, schedule)
        print(f"  Schedule: {len(schedule)} games")

    print(f"  League: {league_id}")
    print(f"  Season: {season_id}")
    print(f"  Teams:  {len(teams)}")
    return conn, league_id, season_id, [t.id for t in teams]


def _create_next_season_cli(conn, league_id: str, current_season_id: str, next_year: int):
    """
    Create the next season record directly in DB (same teams, new schedule).
    Returns (new_season_id, team_ids).
    """
    import datetime
    import uuid as _uuid
    from src.league.schedule import ScheduleGenerator, save_schedule_to_db

    current = conn.execute(
        "SELECT name FROM seasons WHERE id = ?", (current_season_id,)
    ).fetchone()
    current_name = current["name"] if current else f"Season {next_year - 1}"
    parts = current_name.rsplit(" ", 1)
    try:
        new_name = f"{parts[0]} {int(parts[1]) + 1}"
    except (IndexError, ValueError):
        new_name = f"Season {next_year}"

    # Check if already exists
    existing = conn.execute(
        """SELECT ls.season_id FROM league_seasons ls
           JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = ? AND s.year = ?""",
        (league_id, next_year),
    ).fetchone()
    if existing:
        season_id = existing["season_id"]
        team_ids = [r["team_id"] for r in conn.execute(
            "SELECT team_id FROM league_season_teams WHERE league_id = ? AND season_id = ?",
            (league_id, season_id),
        ).fetchall()]
        print(f"  Season {next_year} already exists")
        return season_id, team_ids

    season_id = str(_uuid.uuid4())
    conn.execute("INSERT INTO seasons (id, year, name) VALUES (?, ?, ?)",
                 (season_id, next_year, new_name))
    conn.execute("INSERT INTO league_seasons (league_id, season_id) VALUES (?, ?)",
                 (league_id, season_id))

    team_rows = conn.execute(
        "SELECT team_id FROM league_season_teams WHERE league_id = ? AND season_id = ?",
        (league_id, current_season_id),
    ).fetchall()
    team_ids = [r["team_id"] for r in team_rows]
    for tid in team_ids:
        conn.execute(
            "INSERT OR IGNORE INTO league_season_teams (league_id, season_id, team_id) VALUES (?, ?, ?)",
            (league_id, season_id, tid),
        )

    start_date = datetime.date(next_year, 4, 1)
    rng = __import__("random").Random()
    scheduler = ScheduleGenerator(rng=rng)
    schedule = scheduler.create_schedule(
        season_id=season_id,
        team_ids=team_ids,
        start_date=start_date,
        games_per_matchup=3,
        home_and_away=True,
    )
    save_schedule_to_db(conn, schedule)
    conn.commit()
    print(f"  Created season {next_year}: {len(schedule)} games scheduled")
    return season_id, team_ids


def _play_regular_season(conn, season_id: str, league_id: str, seed: int | None, game_logs: bool):
    """Play all incomplete regular season games."""
    import random
    from argparse import Namespace
    from src.db.repositories.games_repo import GameRepository
    from src.db.repositories.team_game_repo import TeamGameRepository
    from src.db.repositories.team_repo import TeamRepository
    from src.db.repositories.team_rotations_repo import TeamRotationsRepository
    from src.league.play_season import play_game

    league_row = conn.execute("SELECT mode FROM leagues WHERE id = ?", (league_id,)).fetchone()
    league_mode = dict(league_row).get("mode", "blitz") if league_row else "blitz"

    game_repo      = GameRepository(conn)
    team_repo      = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    games = game_repo.get_season_games(
        season_id=season_id, incomplete_only=True, regular_season_only=True
    )
    if not games:
        print("  No incomplete regular season games found")
        return

    rng = random.Random(seed)
    args = Namespace(logs=game_logs)
    completed = 0
    errors = 0

    print(f"  Playing {len(games)} regular season games...")
    for i, game_info in enumerate(games, 1):
        game_dict = dict(game_info)
        try:
            play_game(
                conn=conn, args=args,
                team_repo=team_repo, game_repo=game_repo,
                team_game_repo=team_game_repo, rotations_repo=rotations_repo,
                season_id=season_id, game_info=game_dict, rng=rng,
                league_id=league_id, league_mode=league_mode,
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
        from src.league.offseason.build_season_stats import build_season, ensure_table
        ensure_table(conn)
        n = build_season(conn, season_id)
        print(f"  Stats rollup: {n} rows")
    except Exception as e:
        print(f"  Stats rollup failed (non-fatal): {e}")

    print(f"  Regular season complete: {completed} played, {errors} errors")


def _setup_playoffs(conn, season_id: str, year: int):
    """Seed top 8, build bracket, demote extra starters."""
    import datetime
    from src.league.playoffs.setup_playoffs import get_top_8, build_bracket, demote_extra_starters

    existing = conn.execute(
        "SELECT COUNT(*) FROM series WHERE season_id = ?", (season_id,)
    ).fetchone()[0]
    if existing > 0:
        print("  Playoff bracket already set up")
        return

    seeds = get_top_8(conn, season_id)
    last_game = conn.execute(
        "SELECT MAX(game_date) as d FROM games WHERE season_id = ? AND completed = 1",
        (season_id,),
    ).fetchone()
    from datetime import date, timedelta
    playoff_start = (
        date.fromisoformat(last_game["d"]) + timedelta(days=5)
        if last_game and last_game["d"]
        else date(year, 10, 1)
    )
    demote_extra_starters(conn, season_id, seeds, keep=4)
    build_bracket(conn, season_id, seeds, playoff_start)
    print(f"  Playoff bracket ready. Start date: {playoff_start}")


def _play_playoffs(conn, season_id: str, league_id: str, seed: int | None, game_logs: bool):
    """Play the full playoff bracket to completion."""
    import random
    from argparse import Namespace
    from src.db.repositories.games_repo import GameRepository
    from src.db.repositories.team_game_repo import TeamGameRepository
    from src.db.repositories.team_repo import TeamRepository
    from src.db.repositories.team_rotations_repo import TeamRotationsRepository
    from src.league.playoffs.play_playoffs import (
        get_seeds, get_series_id, play_series, generate_round_games,
        original_seed, _HOME_MAP_BO7, _SEMI_OFFSETS, _FINAL_OFFSETS,
    )

    league_row = conn.execute("SELECT mode FROM leagues WHERE id = ?", (league_id,)).fetchone()
    league_mode = dict(league_row).get("mode", "blitz") if league_row else "blitz"

    rng  = random.Random(seed)
    args = Namespace(logs=game_logs, season_id=season_id)

    game_repo      = GameRepository(conn)
    team_repo      = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    seeds = get_seeds(conn, season_id)

    first_game = conn.execute(
        """SELECT g.game_date FROM games g
           JOIN series s ON g.series_id = s.id
           WHERE s.season_id = ? AND s.name IN ('1v8','2v7','3v6','4v5')
           ORDER BY g.game_date LIMIT 1""",
        (season_id,),
    ).fetchone()
    from datetime import date
    playoff_start = date.fromisoformat(first_game["game_date"]) if first_game else date.today()

    print("  Playing Round 1...")
    r1_winners = {}
    for name, hi, lo in [("1v8", 1, 8), ("2v7", 2, 7), ("3v6", 3, 6), ("4v5", 4, 5)]:
        sid = get_series_id(conn, season_id, name)
        winner = play_series(conn, args, team_repo, game_repo, team_game_repo,
                             rotations_repo, sid, name, best_of=5, rng=rng,
                             league_id=league_id, league_mode=league_mode)
        r1_winners[name] = winner

    print("  Playing Semifinals...")
    semi_winners = []
    for name, team_a, team_b in [
        ("[1,8]v[4,5]", r1_winners["1v8"], r1_winners["4v5"]),
        ("[2,7]v[3,6]", r1_winners["2v7"], r1_winners["3v6"]),
    ]:
        sid = get_series_id(conn, season_id, name)
        sa, sb = original_seed(seeds, team_a), original_seed(seeds, team_b)
        high = team_a if sa < sb else team_b
        low  = team_b if sa < sb else team_a
        generate_round_games(conn, season_id, sid, high, low,
                             _HOME_MAP_BO7, playoff_start, _SEMI_OFFSETS)
        winner = play_series(conn, args, team_repo, game_repo, team_game_repo,
                             rotations_repo, sid, name, best_of=7, rng=rng,
                             league_id=league_id, league_mode=league_mode)
        semi_winners.append((winner, original_seed(seeds, winner)))

    print("  Playing Finals...")
    fa, sa = semi_winners[0]
    fb, sb = semi_winners[1]
    high = fa if sa < sb else fb
    low  = fb if sa < sb else fa
    finals_id = get_series_id(conn, season_id, "Finals")
    generate_round_games(conn, season_id, finals_id, high, low,
                         _HOME_MAP_BO7, playoff_start, _FINAL_OFFSETS)
    champion = play_series(conn, args, team_repo, game_repo, team_game_repo,
                           rotations_repo, finals_id, "Finals", best_of=7, rng=rng,
                           league_id=league_id, league_mode=league_mode)

    champ_name = conn.execute(
        "SELECT city || ' ' || mascot AS name FROM teams WHERE id = ?", (champion,)
    ).fetchone()["name"]
    print(f"  🏆 Champion: {champ_name}")


def _run_offseason_pipeline(conn, season_id: str, league_id: str, seed: int | None):
    """Run the full offseason pipeline (AI snake draft runs for all teams)."""
    import random
    from src.league.offseason.offseason_pipeline import OffseasonPipeline

    rng = random.Random(seed)
    pipeline = OffseasonPipeline(conn, rng)
    # CLI mode: let run_draft execute (all-AI snake draft — do NOT pre-mark done)
    pipeline.run(season_id, league_id=league_id)


def _make_logger(name: str, enabled: bool):
    """Return a logger if enabled, else None."""
    if not enabled:
        return None
    import logging
    from src.util.logger import setup_logger
    return setup_logger(
        name=name, level=logging.INFO,
        console_level=logging.WARNING,
        log_id=name, log_to_file=True,
    )


def _run_reports(db_filename: str, season_id: str, logs: bool = False):
    """Run leaderboard and stats reports by importing directly."""
    from pathlib import Path as _Path
    from src.db.connection import get_connection as _get_conn
    from src.stats.loader import StatsLoader

    db_path = _db_path(db_filename)
    conn = _get_conn(db_filename)

    # --- Season label for display ---
    row = conn.execute(
        "SELECT name, year FROM seasons WHERE id = ?", (season_id,)
    ).fetchone()
    season_label = f"{row['name']} ({row['year']})" if row else season_id[:8]

    # --- Leaderboards (view_leaderboards) ---
    print("  Leaderboards...")
    try:
        from scripts.view_leaderboards import show_all_leaderboards, calculate_min_pa
        from src.stats.loader import StatsLoader
        logger = _make_logger("view_leaderboards", logs)

        min_pa, min_ip = calculate_min_pa(db_path, season_id, logger=logger)

        with StatsLoader(str(db_path)) as loader:
            all_players = loader.load_season_players_with_stats(season_id)
        show_all_leaderboards(all_players, min_pa=min_pa, min_ip=min_ip, logger=logger)
    except Exception as e:
        print(f"  ⚠️  Leaderboards failed: {e}")

    # --- League Totals ---
    print("  League Totals...")
    try:
        from scripts.league_totals import fetch_totals, display as display_totals
        logger = _make_logger("league_totals", logs)
        totals = fetch_totals(conn, season_id)
        display_totals(totals, season_label, logger=logger)
    except Exception as e:
        print(f"  ⚠️  League Totals failed: {e}")

    # --- League Leaders ---
    print("  League Leaders...")
    try:
        from scripts.league_leaders import fetch_leaders, display as display_leaders
        logger = _make_logger("league_leaders", logs)
        with StatsLoader(str(db_path)) as loader:
            all_players = loader.load_season_players_with_stats(season_id)
        leaders = fetch_leaders(all_players, min_pa=min_pa, min_ip=min_ip)
        display_leaders(leaders, season_label, logger=logger)
    except Exception as e:
        print(f"  ⚠️  League Leaders failed: {e}")

    conn.close()


def _run_one_season(conn, db_filename: str, season_id: str, league_id: str,
                    year: int, args) -> None:
    """Play one complete season: regular season → reports → playoffs → offseason."""
    print(f"\n{'='*60}")
    print(f"  Season {year}  (season_id={season_id[:8]}...)")
    print(f"{'='*60}")

    _play_regular_season(conn, season_id, league_id, args.seed, args.game_logs)

    if args.reports:
        print("  Generating reports...")
        _run_reports(db_filename, season_id, logs=args.logs)

    print("  Setting up playoffs...")
    _setup_playoffs(conn, season_id, year)

    print("  Playing playoffs...")
    _play_playoffs(conn, season_id, league_id, args.seed, args.game_logs)

    print("  Running offseason pipeline...")
    _run_offseason_pipeline(conn, season_id, league_id, args.seed)


# ── Command handlers (new-league, run-season) ───────────────────────────────────

def cmd_new_league(args) -> None:
    if not args.yes and not args.clear_db:
        db_p = _db_path(args.db)
        msg = f"⚠️  This will destroy {db_p} and create a fresh league. Continue? [y/N] "
        if input(msg).strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    if args.clear_logs:
        clear_logs()
    if args.clear_temp:
        clear_temp()

    # Always wipe the DB for a fresh league
    clear_db(args.db)

    print(f"\n🏟️  Creating new league — Year {args.year}")
    conn, league_id, season_id, _ = _bootstrap_first_season(args.db, args.year, args.seed)

    current_season_id = season_id
    for n in range(args.num_years):
        year = args.year + n
        if n > 0:
            # Subsequent years: create season directly (teams already exist)
            current_season_id, _ = _create_next_season_cli(
                conn, league_id, current_season_id, year
            )
        _run_one_season(conn, args.db, current_season_id, league_id, year, args)

    print(f"\n✅ Done — {args.num_years} season(s) complete.")


def cmd_run_season(args) -> None:
    db_p = _db_path(args.db)
    if not db_p.exists():
        print(f"❌ DB not found: {db_p}. Use `new-league` to start fresh.")
        sys.exit(1)

    conn = get_connection(args.db)

    # Resolve league
    league_id = args.league_id
    if not league_id:
        rows = conn.execute(
            "SELECT id, name, state FROM leagues ORDER BY rowid"
        ).fetchall()
        if not rows:
            print("❌ No leagues found in DB.")
            sys.exit(1)
        if len(rows) == 1:
            league_id = rows[0]["id"]
            print(f"  Using league: {rows[0]['name']} ({league_id[:8]}...)")
        else:
            league_id = pick_league_interactively(args.db)
            if not league_id:
                sys.exit(0)

    # Find the most recent season for this league
    season_row = conn.execute(
        """SELECT s.id, s.year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ?
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    if not season_row:
        print("❌ No season found for this league.")
        sys.exit(1)

    current_season_id = season_row["id"]
    current_year     = season_row["year"]

    # If a specific year was requested, use that
    start_year = args.year or current_year

    for n in range(args.num_years):
        year = start_year + n
        if year == current_year:
            season_id = current_season_id
        else:
            season_id, _ = _create_next_season_cli(
                conn, league_id, current_season_id, year
            )
            current_season_id = season_id
            current_year = year

        _run_one_season(conn, args.db, season_id, league_id, year, args)

    print(f"\n✅ Done — {args.num_years} season(s) complete.")

# ── Clear handler ──────────────────────────────────────────────────────────────

def cmd_clear(args) -> None:
    if not any([args.logs, args.temp, args.clear_db, args.teams, args.all_teams]):
        print("Nothing to clear — specify at least one of: "
              "--logs, --temp, --db, --teams, --all-teams")
        return

    if args.all_teams:
        confirm = input("⚠️  Delete ALL team files for ALL leagues? [y/N] ").strip()
        if confirm.lower() not in ("y", "yes"):
            print("  Aborted")
            return
        clear_all_teams()

    if args.teams and not args.all_teams:
        league_id = args.league_id or pick_league_interactively(args.db)
        if league_id:
            clear_teams_for_league(league_id)

    if args.clear_db:
        confirm = input(f"⚠️  Delete {args.db}? [y/N] ").strip()
        if confirm.lower() not in ("y", "yes"):
            print("  Aborted")
        else:
            clear_db(args.db)

    if args.logs:
        clear_logs()

    if args.temp:
        clear_temp()


def cmd_reports(args) -> None:
    db_p = _db_path(args.db)
    if not db_p.exists():
        print(f"❌ DB not found: {db_p}")
        sys.exit(1)

    conn = get_connection(args.db)

    # Resolve league
    league_id = args.league_id
    if not league_id:
        rows = conn.execute("SELECT id, name FROM leagues ORDER BY rowid").fetchall()
        if not rows:
            print("❌ No leagues found in DB.")
            sys.exit(1)
        if len(rows) == 1:
            league_id = rows[0]["id"]
        else:
            league_id = pick_league_interactively(args.db)
            if not league_id:
                sys.exit(0)

    # Look up season_id by year
    row = conn.execute(
        """SELECT s.id FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ? AND s.year = ?""",
        (league_id, args.year),
    ).fetchone()
    if not row:
        print(f"❌ No season found for year {args.year} in league {league_id[:8]}...")
        sys.exit(1)

    season_id = row["id"]
    print(f"\n📊 Reports for {args.year} (season {season_id[:8]}...)")
    _run_reports(args.db, season_id, logs=args.logs)
    print("✅ Done.")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "reports":
        cmd_reports(args)

    elif args.command == "clear":
        cmd_clear(args)

    elif args.command == "new-league":
        cmd_new_league(args)

    elif args.command == "run-season":
        cmd_run_season(args)


if __name__ == "__main__":
    main()
