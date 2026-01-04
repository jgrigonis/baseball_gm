"""
Run many games.

python ./src/team/create_team.py -f Team2.csv
python ./src/team/create_team.py -f Team4.csv

To create the teams.

"""

import argparse
import logging

from src.game.event import Event
from src.game.main import Game
from src.team.team import Team
from src.player.player import Player
from src.player.player_formatters import PlayerTableFormatter
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
        "--pauses",
        "-p",
        action="store_true",
        help="Set the pauses flag. Implies debug.",
    )
    parser.add_argument(
        "--innings", "-i", type=int, default=9, help="Set the number of innings."
    )
    parser.add_argument(
        "--games", "-g", type=int, default=2, help="Set the number of games to run."
    )
    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()

    if args.debug:
        levl = logging.DEBUG
    else:
        levl = logging.INFO
    logger = setup_logger(name="details", level=levl)
    logger = logging.getLogger("details")
    home_wins = 0
    away_wins = 0

    home_team = Team("Team", "2")
    home_team.load_team(path="Team2.csv")

    # print("Home Team auto no dh")
    # home_team.set_lineup("auto", False)
    # home_team.display_lineup()

    # print("Home Team auto with dh")
    # home_team.set_lineup("auto", True)
    # home_team.display_lineup()

    # print("Home Team prioritized no dh")
    # home_team.set_lineup(style="prioritized", dh=False)
    # home_team.display_lineup()

    logger.debug("Home Team prioritized with dh")
    home_team.set_lineup(style="prioritized", dh=True)
    home_team.display_lineup()

    # print("Home Team defensive no dh")
    # home_team.set_lineup("defensive", False)
    # home_team.display_lineup()

    # print("Home Team defensive with dh")
    # home_team.set_lineup("defensive", True)
    # home_team.display_lineup()

    # print("Home Team offensive no dh")
    # home_team.set_lineup("offensive", False)
    # home_team.display_lineup()

    # print("Home Team offensive with dh")
    # home_team.set_lineup("offensive", True)
    # home_team.display_lineup()

    away_team = Team("Team", "4")
    away_team.load_team(path="Team4.csv")
    # print("Away Team auto, no dh")
    # away_team.set_lineup(style="auto")
    # away_team.display_lineup()

    # print("Away Team prioritized no dh")
    # away_team.set_lineup(style="prioritized", dh=False)
    # away_team.display_lineup()

    logger.debug("Home Team prioritized with dh")
    away_team.set_lineup(style="prioritized", dh=True)
    away_team.display_lineup()
    for _ in range(args.games):
        my_game = Game(home_team, away_team, args.debug, args.pauses, args.innings)
        my_event = Event(my_game)

        while my_game.game_over is False:
            my_event.do_event()

        logger.info("Home:    " + str(my_game.score.home))
        logger.info("Visitor: " + str(my_game.score.away))

        if my_game.winner == my_game.home:
            home_wins += 1
        if my_game.winner == my_game.away:
            away_wins += 1
    logger.info("-" * 120)
    logger.info(
        PlayerTableFormatter.horizontal_stat_header(
            home_team.city + " " + home_team.mascot
        )
    )
    for player in home_team.lineup:
        logger.info(PlayerTableFormatter.horizontal_stats(player, "season"))
    logger.info("-" * 120)
    logger.info(
        PlayerTableFormatter.horizontal_stat_header(
            away_team.city + " " + away_team.mascot
        )
    )
    for player in away_team.lineup:
        logger.info(PlayerTableFormatter.horizontal_stats(player, "season"))
    logger.info("-" * 120)
    logger.info(
        PlayerTableFormatter.horizontal_pitching_stat_header(
            home_team.city + " " + home_team.mascot
        )
    )
    for player in home_team.players:
        if player.season_stats.stats.pitching.outs > 0:
            logger.info(
                PlayerTableFormatter.horizontal_pitching_stats(player, "season")
            )

    logger.info(
        PlayerTableFormatter.horizontal_pitching_stat_header(
            away_team.city + " " + away_team.mascot
        )
    )
    for player in away_team.players:
        if player.season_stats.stats.pitching.outs > 0:
            logger.info(
                PlayerTableFormatter.horizontal_pitching_stats(player, "season")
            )
    logger.info("-" * 120)
    logger.info(
        PlayerTableFormatter.horizontal_defensive_stat_header(
            home_team.city + " " + home_team.mascot
        )
    )
    # home teamdefensive stats here
    for player in home_team.players:
        if player.season_stats.stats.fielding.chances > 0:
            logger.info(
                PlayerTableFormatter.horizontal_defensive_stats(player, "season")
            )
    logger.info("-" * 120)
    logger.info(
        PlayerTableFormatter.horizontal_defensive_stat_header(
            away_team.city + " " + away_team.mascot
        )
    )
    # away team defensive stats here
    for player in away_team.players:
        if player.season_stats.stats.fielding.chances > 0:
            logger.info(
                PlayerTableFormatter.horizontal_defensive_stats(player, "season")
            )
    logger.info("-" * 120)
    logger.info("Home wins:" + str(home_wins))
    logger.info("Away wins:" + str(away_wins))


if __name__ == "__main__":
    main()
