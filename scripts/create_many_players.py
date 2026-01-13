"""
Create a bunch of players (default=40), print out the best players in each
skill category or position rating.

They aren't saved anywhere

"""

import argparse

from src.player.player_factory import PlayerFactory
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
    pf = PlayerFactory()

    print(PlayerTableFormatter.header_skills())
    for _ in range(args.number):
        my_player = pf.create()
        print(PlayerTableFormatter.hor_skills(my_player))


if __name__ == "__main__":
    main()
