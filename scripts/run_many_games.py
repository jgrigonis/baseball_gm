"""
Run many games.

Create Team(s) you are going to use
python ./src/team/create_team.py -f Team1.csv
python ./src/team/create_team.py -f Team2.csv
python ./src/team/create_team.py -f Team4.csv
python ./src/team/create_team.py -f Giants.csv

To create the teams.

"""

import argparse
import logging
import os
import sqlite3
import uuid

from src.db.init import init_db
from src.db.repositories.player_games import PlayerGameRepository
from src.game.event_generator import Event
from src.game.game import Game
from src.stats.stats import Stats
from src.stats.stats import SeasonStats
from src.team.team_factory import Team
from src.player.player_formatters import PlayerTableFormatter
from src.util.locations import TEAM_FILES_DIR
from src.util.logger import setup_logger

HOME_FILE = TEAM_FILES_DIR + os.sep + "Team1.csv"
AWAY_FILE = TEAM_FILES_DIR + os.sep + "Giants.csv"
LEAGUE_DIR = "leagues"


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
        "--games", "-g", type=int, default=1, help="Set the number of games to run."
    )
    parser.add_argument(
        "--league",
        "-l",
        default="league.db",
        help="Set the league database file.",
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
    home_wins = 0
    away_wins = 0

    conn = sqlite3.connect(LEAGUE_DIR + os.sep + args.league)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    player_games_repo = PlayerGameRepository(conn)

    home_team = Team("San Francisco", "Giants")
    home_team.load_team(path=HOME_FILE)
    logger.debug("Home Team prioritized with dh")
    home_team.set_lineup(style="prioritized", dh=True)
    home_team.display_lineup()

    away_team = Team("Team", "1")
    away_team.load_team(path=AWAY_FILE)
    logger.debug("Away Team prioritized with dh")
    away_team.set_lineup(style="prioritized", dh=True)
    away_team.display_lineup()

    for _ in range(args.games):
        my_game = Game(home_team, away_team, levl, args.pauses, args.innings)
        my_event = Event(my_game)
        game_id = uuid.uuid4().hex
        logger.info("Game ID = {}".format(game_id))

        while my_game.game_over is False:
            my_event.do_event()

        logger.info("Home:    " + str(my_game.score.home))
        logger.info("Visitor: " + str(my_game.score.away))

        if my_game.winner == my_game.home:
            home_wins += 1
        if my_game.winner == my_game.away:
            away_wins += 1

        # Insert game data for each player into repo
        for player in away_team.players + home_team.players:
            player_games_repo.insert(
                game_id=game_id,
                player_id=player.id,
                team_id=1,
                opponent_team_id=2,
                stats=player.game_stats,
            )

        # for player in home_team.players:
        #     player_games_repo.insert(
        #         game_id=game_id,
        #         player_id=player.id,
        #         team_id=2,
        #         opponent_team_id=1,
        #         stats=player.stats,
        #     )

    # for player in home_team.players + away_team.players:
    #     rows = player_games_repo.fetch_player_games(player_id=player.id)
    #     game_stats = []
    #     for row in rows:
    #         game_stats.append(row)
    #     stats = Stats()
    #     for gs in game_stats:
    #         stats.add(gs)

    #     player.season_stats = SeasonStats(
    #         stats=stats,
    #         games_played=len(game_stats)
    #     )

    # Eventually: player.season_stats = season_stats_loader.load_for_player(player.id)
    for player in home_team.players + away_team.players:
        rows = player_games_repo.fetch_player_games(player_id=player.id)

        stats = Stats()
        for row in rows:
            stats.add(row)

        player.season_stats = SeasonStats(stats=stats, games_played=len(rows))

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
