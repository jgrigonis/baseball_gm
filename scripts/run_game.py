"""
Run one game.

This won't persist results in the DB

python ./src/team/create_team.py -f Team1.csv
python ./src/team/create_team.py -f Team2.csv

"""

import argparse
import logging

from src.game.event import Event
from src.game.main import Game
from src.team.team import Team
from src.util.logger import setup_logger


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
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()
    levl = logging.INFO
    if args.debug:
        levl = logging.DEBUG
    if args.trace:
        levl = logging.TRACE
    logger = setup_logger(name="details", level=levl, console_level=levl)
    logger = logging.getLogger("details")
    # Set up Home Team
    home_team = Team("Team", "One")
    home_team.load_team(path="Team1.csv")

    logger.debug("Home Team prioritized positions offensive lineup")
    home_team.set_lineup("prioritized")
    home_team.display_lineup()

    # Set up Away Team
    away_team = Team("Team", "Two")
    away_team.load_team(path="Team2.csv")

    logger.debug("Away Team Auto Set")
    away_team.set_lineup()
    away_team.display_lineup()

    logger.debug("Away Team defensive lineup")
    away_team.set_lineup("defensive")
    away_team.display_lineup()

    logger.debug("Away Team offensive lineup")
    away_team.set_lineup("offensive")
    away_team.display_lineup()

    logger.debug("Away Team prioritized positions offensive lineup")
    away_team.set_lineup("prioritized")
    away_team.display_lineup()

    my_game = Game(home_team, away_team, levl, args.pauses, args.innings)
    my_event = Event(my_game)

    while my_game.game_over is False:
        my_event.do_event()

    logger.info("Home:    " + str(my_game.score.home))
    logger.info("Visitor: " + str(my_game.score.away))


if __name__ == "__main__":
    main()
