# src/league/cli.py
import argparse
import datetime

# from datetime import date
from pathlib import Path
import sqlite3
import sys

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
from src.util.locations import LEAGUE_FILES_DIR


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
    parser.add_argument("--db", "-d", default="league.db", help="DB File Name")
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

    args = parser.parse_args()
    return args


def main():
    args = get_args()

    # import time

    # print(f"========== SCRIPT START {time.time()} ==========")

    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / args.db)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    boot = LeagueBootstrapper(conn)
    manifest = load_manifest(Path(LEAGUE_FILES_DIR) / args.manifest)
    try:
        validate_manifest_structure(manifest)
        validate_manifest_uniqueness(manifest)
    except ValueError as e:
        print(e)
        sys.exit(1)
    missing = find_missing_team_files(manifest)
    if missing and args.create:
        create_team_files(missing)
    elif missing:
        for miss in missing:
            print(f"The csv file for {miss} is missing.")
        sys, exit(1)
    try:
        league_id, teams, season_id = boot.bootstrap_from_manifest(manifest)
    except RuntimeError as e:
        print(e)
        sys.exit(1)

    print(f"League created: {league_id}")
    print(f"Season created: {season_id}")
    print(f"Teams imported: {len(teams)}")

    existing_games = conn.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = ?", (season_id,)
    ).fetchone()[0]

    if existing_games > 0 and not args.regenerate_schedule:
        print(f"Schedule already exists: {existing_games} games")
        return
    elif existing_games > 0 and args.regenerate_schedule:
        conn.execute("DELETE FROM games WHERE season_id = ?", (season_id,))
        conn.commit()
        print(f"Deleted {existing_games} existing games")

    team_ids = [team.id for team in teams]

    # Parse start date from manifest or default
    start_date_str = manifest.get(
        "season_start_date", f"{manifest.get('season_year', 2028)}-04-01"
    )
    start_date = datetime.datetime.fromisoformat(start_date_str).date()

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

    # conn.executescript(
    #     """
    # SELECT COUNT(*) FROM leagues;
    # SELECT COUNT(*) FROM seasons;
    # SELECT season_id, COUNT(*) FROM games GROUP BY season_id;
    # """
    # )


if __name__ == "__main__":
    main()
