"""
Create a bunch of players, print out the best ratings in each
skill category or position rating.

Doesn't save the players anywhere

"""

import argparse
from copy import deepcopy

from src.player.player_evaluator import EXPECTED_RATINGS
from src.player.player_factory import PlayerFactory
from src.player.player_in_game import PlayerInGame
from src.player.positions import SKILLS


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
    maxes = deepcopy(dict(SKILLS))
    max_ratings = {}
    for item in EXPECTED_RATINGS:
        max_ratings[item] = 0
    best_skills = []
    best_ratings = []
    pf = PlayerFactory()
    for _ in range(players_to_create):
        pr = pf.create()
        pig = PlayerInGame(pr)
        for key in pr.skills.as_dict():
            if pr.skills[key] > maxes[key]:
                maxes[key] = pr.skills[key]
                best_skills.append(pr)
        for key in max_ratings:
            if pig.ratings[key] > max_ratings[key]:
                max_ratings[key] = pig.ratings[key]
                best_ratings.append(pig)

    print(f"Maxes = {maxes}")


if __name__ == "__main__":
    main()
