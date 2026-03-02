# scripts/export_as_csv.py

import argparse
from pathlib import Path

from src.util.locations import TEAM_FILES_DIR
from src.team.team_factory import TeamFactory
from src.io.player_csv_exporter import PlayerCSVExporter


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--city",
        "-c",
        default="Default",
        help="Set the city name.",
    )
    parser.add_argument("--mascot", "-m", default="Mascot", help="Set the mascot name.")
    parser.add_argument(
        "--filename", "-f", default="default-mascot.csv", help="Set the file name."
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    tf = TeamFactory()

    tr = tf.generate_team(city=args.city, mascot=args.mascot)
    PlayerCSVExporter.write(tr, Path(TEAM_FILES_DIR) / args.filename)


if __name__ == "__main__":
    main()
