"""
Run one game.

"""
import argparse

from src.game.event import Event
from src.game.main import Game


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
    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()
    my_game = Game(args.debug, args.pauses, args.innings)
    my_event = Event(my_game, args.debug)

    while my_game.game_over is False:
        my_event.do_event()
    
    print("Home:    " + str(my_game.score.home))
    print("Visitor: " + str(my_game.score.away))

if __name__ == "__main__":
    main()
