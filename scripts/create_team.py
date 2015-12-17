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

from name_generator.names import NameGenerator
from player.player import Player
from player import positions
from team.team import Team
__author__ = 'jgrigonis'


def main():
    debug = False
    ng = NameGenerator()
    team = Team("Foo", "Bars")
    # These loops could be made into a function
    for _ in range(2):
        my_player = Player(ng.first(), ng.last(), position='c')
        my_player.generate()
        team.players.append(my_player)
    for _ in range(5):
        position=random.choice(['of', 'cf', 'lf', 'rf'])
        my_player = Player(ng.first(), ng.last(), position=position)
        my_player.generate()
        team.players.append(my_player)
    for _ in range(6):
        position = random.choice(['if', '2b', '3b', 'ss', '1b'])
        my_player = Player(ng.first(), ng.last(), position=position)
        my_player.generate()
        team.players.append(my_player)
    for _ in range(5):
        my_player = Player(ng.first(), ng.last(), position='sp')
        my_player.generate()
        team.players.append(my_player)
    for _ in range(7):
        my_player = Player(ng.first(), ng.last(), position='rp')
        my_player.generate()
        team.players.append(my_player)
    for _ in range(4):
        position = random.choice(['sp', 'rp'])
        my_player = Player(ng.first(), ng.last(), position=position)
        my_player.generate()
        team.players.append(my_player)
    for _ in range(11):
        position = random.choice(positions)
        my_player = Player(ng.first(), ng.last(), position=position)
        my_player.generate()
        team.players.append(my_player)
    if debug:
        for player in team.players:
            print(player)
    print(Player.header())
    for player in team.players:
        print(player.horizontal())

if __name__ == "__main__":
    main()
