"""
Create a randomly named player. Give him random skills.
Determine his best position.

"""

import argparse

from src.player import positions
from src.player.player import Player
from src.name_generator.names import NameGenerator


def create(position=None):
    ng = NameGenerator()
    my_player = Player(ng.first("male"), ng.last(), position=position)
    my_player.generate()
    return my_player


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--position", "-p", default=None, choices=positions, help="The player position."
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    my_player = create(args.position)
    # Print the player
    if args.debug:
        print(my_player)
    print(my_player.header())
    print(my_player.horizontal())


if __name__ == "__main__":
    main()
