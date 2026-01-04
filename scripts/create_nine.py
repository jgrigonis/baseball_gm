"""
Create a team of 9 players.
1 of each position

This will also write out a csv file called TeamNine.csv that represents the
team and has all its ratings.

"""

from src.player.create import create

from src.player.player import Player
from src.player.player_formatters import PlayerTableFormatter
from src.team.team import Team

__author__ = "josh"


def main():
    debug = False
    team = Team("Team", "Nine")
    team.players.append(create("c"))
    team.players.append(create("cf"))
    team.players.append(create("lf"))
    team.players.append(create("rf"))
    team.players.append(create("ss"))
    team.players.append(create("2b"))
    team.players.append(create("3b"))
    team.players.append(create("1b"))
    team.players.append(create("sp"))
    print(Player.legend())
    if debug:
        for player in team.players:
            print(player)
    print(Player.header())
    for player in team.players:
        print(PlayerTableFormatter.horizontal(player))
    with open("TeamNine.csv", "w") as csv:
        csv.writelines(PlayerTableFormatter.csv_header())
        for player in team.players:
            csv.writelines(PlayerTableFormatter.csv(player))


if __name__ == "__main__":
    main()
