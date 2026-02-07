# scripts/run_game_from_csv.py

"""
Run one game.

Load 2 random teams from csv files

Make them play.

We can discard the results.

"""

import argparse
import logging
from pathlib import Path

# from src.game.event_generator import Event
from src.game.game import Game
from src.team.team_factory import TeamFactory
from src.team.team_in_game_factory import TeamInGameFactory

from src.util.locations import TEAM_FILES_DIR

# from src.util.logger import setup_logger

HOME_FILE = Path(TEAM_FILES_DIR) / "amsterdam.csv"
AWAY_FILE = Path(TEAM_FILES_DIR) / "bangkok.csv"
HOME_CITY = "Amsterdam"
HOME_MASCOT = "Homers"
AWAY_CITY = "Bangkok"
AWAY_MASCOT = "Visitoors"


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
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    levl = logging.INFO
    if args.debug:
        levl = logging.DEBUG
    if args.trace:
        levl = logging.TRACE
    # logger = setup_logger(name="details", level=levl, console_level=levl)
    # logger = logging.getLogger("details")
    tf = TeamFactory(log_level=levl)
    # Set up Home Team Record
    home_team_record = tf.from_csv(path=HOME_FILE, city=HOME_CITY, mascot=HOME_MASCOT)

    # Set up Away Team Record
    away_team_record = tf.from_csv(path=AWAY_FILE, city=AWAY_CITY, mascot=AWAY_MASCOT)

    # setup TeamInGame objects
    home_team = TeamInGameFactory.from_record(home_team_record)
    away_team = TeamInGameFactory.from_record(away_team_record)

    # set lineups
    home_team.set_lineup()
    away_team.set_lineup()

    my_game = Game(
        home_team=home_team, away_team=away_team, log_level=levl, pauses=args.pauses
    )
    result = my_game.play()

    print(home_team.output_defensive_stats())
    print(away_team.output_defensive_stats())

    print(home_team.output_lineup_ratings())
    print(home_team.output_pitcher_ratings())
    print(away_team.output_lineup_ratings())
    print(away_team.output_pitcher_ratings())

    print(home_team.output_lineup_skills())
    print(home_team.output_pitcher_skills())
    print(away_team.output_lineup_skills())
    print(away_team.output_pitcher_skills())

    print(home_team.output_batting_stats())
    print(away_team.output_batting_stats())

    print(home_team.output_pitching_stats())
    print(away_team.output_pitching_stats())

    return result


if __name__ == "__main__":
    main()
