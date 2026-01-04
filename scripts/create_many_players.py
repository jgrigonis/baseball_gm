"""
Create a bunch of players (default=40), print out the best players in each
skill category or position rating.

They aren't saved anywhere

"""

import argparse

from src.player.player import Player
from src.name_generator.names import NameGenerator
from src.player.create import create
from src.player.player_formatters import PlayerTableFormatter


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--number", "-n", type=int, default=40, help="The number of players to create."
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    debug = args.debug
    if not debug:
        my_player = create()
        print(my_player.header())
    for _ in range(args.number):
        my_player = create()
        # Print the player
        if debug:
            print(my_player)
            print(my_player.header())
        print(PlayerTableFormatter.horizontal(my_player))


if __name__ == "__main__":
    main()
