# src/league/cli.py
import argparse
import datetime
import random

# from datetime import date
from pathlib import Path
import sys

from src.db.connection import get_connection
from src.db.init import init_db
from src.league.bootstrap import LeagueBootstrapper
from src.league.manifest_helper import (
    load_manifest,
    validate_manifest_structure,
    validate_manifest_uniqueness,
    find_missing_team_files,
    create_team_files,
)
from src.league.schedule import ScheduleGenerator, save_schedule_to_db
from src.util.locations import MANIFEST_FILES_DIR

sys.stdout.reconfigure(encoding="utf-8")


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--create",
        "-c",
        default=False,
        action="store_true",
        help="Create missing csv files.",
    )
    parser.add_argument(
        "--update-rosters",
        "-u",
        default=False,
        action="store_true",
        help="Allow importing updated roster CSVs (e.g. after offseason aging).",
    )
    parser.add_argument("--db", "-d", default="cli.db", help="DB File Name")
    parser.add_argument(
        "--manifest", "-m", default="league_teams.json", help="Set the manifest file."
    )
    parser.add_argument(
        "--regenerate-schedule",
        "-r",
        default=False,
        action="store_true",
        help="Regenerate schedule if it exists",
    )
    parser.add_argument(
        "--seed", "-s", type=int, help="Random seed for reproducibility"
    )

    args = parser.parse_args()
    return args


def main():
    args = get_args()

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    print(f"🎲 Seed: {seed}")
    rng = random.Random(seed)

    # import time
    # print(f"========== SCRIPT START {time.time()} ==========")
    man_path = Path(MANIFEST_FILES_DIR)

    conn = get_connection(args.db)

    init_db(conn)

    boot = LeagueBootstrapper(conn, rng=rng)
    manifest = load_manifest(man_path / args.manifest)
    try:
        validate_manifest_structure(manifest)
        validate_manifest_uniqueness(manifest)
    except ValueError as e:
        print(e)
        sys.exit(1)
    missing = find_missing_team_files(manifest)
    year = manifest.get("season_year", 2028)
    if missing and args.create:
        create_team_files(missing, year, rng=rng)
    elif missing:
        for miss in missing:
            print(f"The csv file for {miss} is missing.")
        sys, exit(1)

    # Parse start date from manifest or default
    start_date_str = manifest.get(
        "season_start_date",
        f"{year}-04-01",  # default to april 1
    )
    start_date = datetime.datetime.fromisoformat(start_date_str).date()

    try:
        league_id, teams, season_id = boot.bootstrap_from_manifest(
            manifest, start_date, allow_roster_update=args.update_rosters
        )
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    print(f"League created: {league_id}")
    print(f"Season created: {season_id}")
    print(f"Teams imported: {len(teams)}")

    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = %s", (season_id,)
    ).fetchone()["count"]

    if existing_games > 0 and not args.regenerate_schedule:
        print(f"Schedule already exists: {existing_games} games")
        return
    elif existing_games > 0 and args.regenerate_schedule:
        conn.execute("DELETE FROM games WHERE season_id = %s", (season_id,))
        conn.commit()
        print(f"Deleted {existing_games} existing games")

    team_ids = [team.id for team in teams]

    scheduler = ScheduleGenerator()
    schedule = scheduler.create_schedule(
        season_id=season_id,
        team_ids=team_ids,
        start_date=start_date,
        games_per_matchup=3,
        home_and_away=True,
    )

    save_schedule_to_db(conn, schedule)
    print(f"Schedule generated: {len(schedule)} games")


if __name__ == "__main__":
    main()
