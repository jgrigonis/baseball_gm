# src/league/cli.py
import argparse
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
    args = parser.parse_args()
    return args


def main():
    args = get_args()
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


if __name__ == "__main__":
    main()
