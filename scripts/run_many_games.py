"""
Run many games.

"""
import argparse

from src.game.event import Event
from src.game.main import Game
from src.team.team import Team


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d",
        action='store_true',
        help="Set the debug flag."
    )
    parser.add_argument(
        "--pauses", "-p",
        action='store_true',
        help="Set the pauses flag. Implies debug."
    )
    parser.add_argument(
        "--innings", "-i",
        type=int,
        default=9,
        help="Set the number of innings."
    )
    parser.add_argument(
        "--games", "-g",
        type=int,
        default=2,
        help="Set the number of games to run."
    )
    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()
    for _ in range(args.games):
        home_team = Team("Portland", "Beavers")
        away_team = Team("Portland", "Beavers")
        home_team.load_team()
        home_team.set_lineup()
        away_team.load_team()
        away_team.set_lineup()

        my_game = Game(home_team, away_team, args.debug, args.pauses, args.innings)
        my_event = Event(my_game, args.debug)

        while my_game.game_over is False:
            my_event.do_event()
        
        print("Home:    " + str(my_game.score.home))
        print("Visitor: " + str(my_game.score.away))
        print("-" * 20)

if __name__ == "__main__":
    main()
