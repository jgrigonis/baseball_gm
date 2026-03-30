# scripts/list_seasons.py

import argparse

from src.db.connection import get_connection
from src.db.repositories.season_repo import SeasonRepository


def parse_args():
    parser = argparse.ArgumentParser(
        description="List all seasons in a league database."
    )
    parser.add_argument(
        "--db",
        "-d",
        default="cli.db",
        help="DB filename (default: cli.db)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    conn = get_connection(args.db)
    sr = SeasonRepository(conn)

    seasons = sr.get_all_seasons()
    if not seasons:
        print("No seasons found.")
        return

    for season in seasons:
        print(season)


if __name__ == "__main__":
    main()
