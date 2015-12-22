"""Create a team.
For now, we'll just create a random 40 man roster.
2 catchers
5 outfielders - random selection
6 infielders - random selection
16 pitchers - 5 starters, 7 relief, 4 random
11 other randoms

Might be useful to write this out to files soon. The data would be much
easier to visualize in a spreadsheet.

Need to move the loops into the Team class, so we just tell it a number
for each position, and then it generates the team.

Need to do something about setting the lineup.
"""
import random

from scripts.create_player import create
import game.game_exceptions as game_exceptions
from player.player import Player
from player import positions
from team.team import Team
__author__ = 'jgrigonis'


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


def main():
    debug = False
    team = Team("Foo", "Bars")
    team.players.extend(create_players('c', 2))
    team.players.extend(create_players(['of', 'cf', 'lf', 'rf'], 5))
    team.players.extend(create_players(['if', '2b', '3b', 'ss', '1b'], 6))
    team.players.extend(create_players('sp', 5))
    team.players.extend(create_players('rp', 7))
    team.players.extend(create_players(['sp', 'rp'], 4))
    team.players.extend(create_players(num=11))
    if debug:
        for player in team.players:
            print(player)
    print(Player.header())
    for player in team.players:
        print(player.horizontal())
    with open('FooBars.csv', 'w') as csv:
        csv.writelines(Player.csv_header())
        for player in team.players:
            csv.writelines(player.csv())

if __name__ == "__main__":
    main()
