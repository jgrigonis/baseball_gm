"""
Create a bunch of players, print out the best players in each
skill category or position rating.

Doesn't save the players anywhere

"""

import argparse

from src.player.player import Player, skills
from src.player.__init__ import rated_positions
from scripts.create_player import create
from copy import deepcopy


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
    players_to_create = args.number
    maxes = deepcopy(skills)
    max_ratings = {}
    for item in rated_positions:
        max_ratings[item] = 0
    best_players = {}
    print(Player.header())
    for x in range(players_to_create):
        player = create()

        for key in player.skills:
            if player.skills[key] > maxes[key]:
                maxes[key] = player.skills[key]
                best_players[key] = deepcopy(player)
        for key in max_ratings:
            if player.ratings[key] > max_ratings[key]:
                max_ratings[key] = player.ratings[key]
                best_players[key] = deepcopy(player)
        if debug:
            print(player.horizontal())

    for key in best_players:
        if key in rated_positions:
            print(key + " (" + str(best_players[key].ratings[key]) + ")" + ": ")
            print(best_players[key].horizontal())
        else:
            print(key + " (" + str(best_players[key].skills[key]) + ")" + ": ")
            print(best_players[key].horizontal())


if __name__ == "__main__":
    main()
