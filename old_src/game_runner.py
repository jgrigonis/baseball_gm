# src/game/game_runner.py

"""
Runner
 └── Game
      ├── EventGenerator
      ├── Resolver
      └── Rules

GameRunner

Loads one game
Plays one game
Returns one result
"""


import argparse
import logging
from pathlib import Path


from src.team.team_factory import TeamFactory
from src.team.team_in_game_factory import TeamInGameFactory

from src.game.game import Game
from src.util.locations import TEAM_FILES_DIR
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
    parser.add_argument(
        "--league",
        "-l",
        default=None,
        help="Set the league database file.",
    )

    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def set_debug(debug, trace):
    levl = logging.INFO
    if debug:
        levl = logging.DEBUG
    if trace:
        levl = logging.TRACE
    return levl


def set_logger(levl):
    logger = setup_logger(name="details", level=levl, console_level=levl)
    logger = logging.getLogger("details")
    return logger


def load_team_from_csv(path: str, *, city: str, mascot: str):
    team_factory = TeamFactory()
    team_record = team_factory.from_csv(
        path=path,
        city=city,
        mascot=mascot,
    )
    return TeamInGameFactory.from_record(team_record)


class GameRunner:
    def __init__(self, *, innings=9, pauses=False, level=None):
        self.innings = innings
        self.pauses = pauses
        self.level = level

    def run_game(self, home_team, away_team):
        game = Game(
            home_team=home_team,
            away_team=away_team,
            innings=self.innings,
            pauses=self.pauses,
            level=self.level,
        )
        game.play()
        return game.results()


def main():
    args = get_args()
    levl = set_debug(args.debug, args.trace)
    logger = set_logger(levl)

    # League play
    # team_record = team_repo.load(team_id)
    # team = TeamInGameFactory.from_record(team_record)

    print("Loading Teams")
    home_team = load_team_from_csv(
        Path(TEAM_FILES_DIR) / "team_one.csv",
        city="San Francisco",
        mascot="Giants",
    )
    away_team = load_team_from_csv(
        Path(TEAM_FILES_DIR) / "team_one.csv",
        city="Los Angeles",
        mascot="Dodgers",
    )

    # quit()
    # home_record = TeamRecord(...)
    # away_record = TeamRecord(...)

    # home = TeamInGameFactory.from_record(home_record)
    # away = TeamInGameFactory.from_record(away_record)

    # game = Game(home, away)

    runner = GameRunner(
        innings=args.innings,
        pauses=args.pauses,
        level=levl,
    )

    results = runner.run_game(home_team, away_team)

    print(results)

    # Writing stats:
    # stats_repo.apply_results(results)
    # player_repo.apply_fatigue(results)


if __name__ == "__main__":
    main()


# from src.db.repositories.player_repo import PlayerRepository
# from src.db.repositories.team_repo import TeamRepository
# from src.game.game import Game
# from src.team.team_factory import Team
# from src.util.locations import TEAM_FILES_DIR


# # def setup_teams(home_file, away_file, logger):
# #     home_team = Team("San Francisco", "Giants")
# #     home_team.load_team(path=home_file)
# #     logger.debug("Home Team prioritized with dh")
# #     home_team.set_lineup(style="prioritized", dh=True)
# #     home_team.display_lineup()

# #     away_team = Team("Team", "1")
# #     away_team.load_team(path=away_file)
# #     logger.debug("Away Team prioritized with dh")
# #     away_team.set_lineup(style="prioritized", dh=True)
# #     away_team.display_lineup()


# def main():
#     args = get_args()
#     levl = set_debug(args.debug, args.trace)
#     logger = set_logger(levl)

#     # team_repo = TeamRepository(conn)
#     # player_repo = PlayerRepository(conn)
#     # home_team = team_repo.load_for_game(home_team_id)
#     # away_team = team_repo.load_for_game(away_team_id)
#     game = Game(
#         home_team=home_team,
#         away_team=away_team,
#         level=levl,
#         pauses=args.pauses,
#         innings=args.innings,
#     )

#     game.play()
#     results = game.results()

#     # stats_repo.record_game(results)
#     player_repo.apply_fatigue(results)


# if __name__ == "__main__":
#     main()
