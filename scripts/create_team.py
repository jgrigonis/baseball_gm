"""
Create a team.
For now, we'll just create a random 40 man roster.
2 catchers
5 outfielders - random selection
6 infielders - random selection
16 pitchers - 5 starters, 7 relief, 4 random
11 other randoms

Need to move the create_players into the Team class.

Need to do something about setting the lineup.

If we let users create a team in "competition" mode we probably want to
limit the number of center fielders as it is objectively better than
the other outfield positions. Same with ss, 2b, etc.

Perhaps something like this:

2 cf
2 lf
2 rf
2 ss
2 2b
2 1b
2 3b
8 sp

remaining players must be: if, of, rp or c

This will also write out a csv file called FooBars.csv that represents the
team and has all its ratings.

"""

import argparse
import random

from scripts.create_player import create
import src.game.game_exceptions as game_exceptions
from src.player.player import Player
from src.player import positions
from src.team.team import Team

__author__ = "josh"


def create_players(position=None, num=1):
    players = []
    for _ in range(num):
        if position is None:
            pos = random.choice(positions)
        elif isinstance(position, list):
            pos = random.choice(position)
        else:
            pos = position
        if pos not in positions:
            raise game_exceptions.BadPositionException()
        players.append(create(pos))
    return players


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    debug = args.debug
    team_file = ("FooBars.csv",)
    team = Team("Foo", "Bars")
    team.players.extend(create_players("c", 2))
    team.players.extend(create_players(["of", "cf", "lf", "rf"], 5))
    team.players.extend(create_players(["if", "2b", "3b", "ss", "1b"], 6))
    team.players.extend(create_players("sp", 5))
    team.players.extend(create_players("rp", 7))
    team.players.extend(create_players(["sp", "rp"], 4))
    team.players.extend(create_players(num=11))
    if debug:
        for player in team.players:
            print(player)
    print(Player.header())
    for player in team.players:
        print(player.horizontal())
    with open("FooBars.csv", "w") as csv:
        csv.writelines(Player.csv_header())
        for player in team.players:
            csv.writelines(player.csv())


if __name__ == "__main__":
    main()
