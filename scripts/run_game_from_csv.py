# scripts/run_game_from_csv.py

"""
Run one game.

Load 2 random teams from csv files

Make them play.

We can discard the results.

"""

import argparse
from pathlib import Path

from scripts.run_game import main as game_runner
from src.io.player_csv_importer import PlayerCSVImporter
from src.team.team_record import TeamRecord
from src.util.locations import TEAM_FILES_DIR

HOME_FILE = Path(TEAM_FILES_DIR) / "2025" / "hong_kong.csv"
HOME_CITY = "Hong Kong"
HOME_MASCOT = "Homers"

AWAY_FILE = Path(TEAM_FILES_DIR) / "2025" / "amsterdam.csv"
AWAY_CITY = "Amsterdam"
AWAY_MASCOT = "Aardvarks"


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--trace", "-t", action="store_true", help="Higher level of debugging."
    )
    parser.add_argument(
        "--pauses",
        "-p",
        action="store_true",
        help="Set the pauses flag. Implies debug.",
    )
    parser.add_argument(
        "--innings", "-i", type=int, default=9, help="Set the number of innings."
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None, help="RNG seed for reproducibility."
    )
    args = parser.parse_args()
    args.home = load_team(HOME_FILE, HOME_CITY, HOME_MASCOT)
    args.away = load_team(AWAY_FILE, AWAY_CITY, AWAY_MASCOT)
    return args


def load_team(path: Path, city: str, mascot: str) -> TeamRecord:
    players = tuple(PlayerCSVImporter.read(path))
    return TeamRecord(
        id=str(path.stem),
        city=city,
        mascot=mascot,
        players=players,
        source_csv=path,
    )


def main():
    args = get_args()
    result = game_runner(args)
    print(result)


if __name__ == "__main__":
    main()
