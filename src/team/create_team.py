"""
Create a team.
For now, we'll just create a random 40 man roster.

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

This will also write out a csv file that represents the
team and has all its ratings.

"""

import argparse
import os

from src.player.create import create_players

# from src.player.player import Player
from src.player.player_formatters import PlayerTableFormatter
from src.team.team import Team
from src.util.locations import TEAM_FILES_DIR

__author__ = "josh"


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--file", "-f", default=None, required=True, help="Set the team csv file."
    )
    parser.add_argument("--city", "-c", default="Foo", help="Set the team city.")
    parser.add_argument("--mascot", "-m", default="Bars", help="Set the team mascot.")
    args = parser.parse_args()
    return args


def create_team():
    """Create a team."""
    args = get_args()
    debug = args.debug

    files = os.listdir(TEAM_FILES_DIR)
    if args.file in files:
        print(f"ERROR: {args.file} already exists.")
        quit()

    team = Team(args.city, args.mascot)

    team.players.extend(create_players("c", 2))  # 2 catchers
    team.players.extend(create_players("cf"))
    team.players.extend(create_players("rf"))
    team.players.extend(create_players("lf"))
    team.players.extend(
        create_players(["of", "cf", "lf", "rf"], 2)
    )  # 2 more random outfielders
    team.players.extend(create_players("2b"))
    team.players.extend(create_players("3b"))
    team.players.extend(create_players("ss"))
    team.players.extend(create_players("1b"))
    team.players.extend(
        create_players(["if", "2b", "3b", "ss", "1b"], 2)
    )  # 2 more random infielders
    team.players.extend(create_players("sp", 5))  # 5 starting pitchers
    team.players.extend(create_players("rp", 7))  # 7 relief pitchers
    team.players.extend(create_players(["sp", "rp"], 4))  # 4 more pitchers
    team.players.extend(create_players(num=11))  # 11 more random players
    if debug:
        print(PlayerTableFormatter.header())
        for player in team.players:
            print(PlayerTableFormatter.horizontal(player))

    with open(TEAM_FILES_DIR + os.sep + args.file, "w") as csv:
        csv.writelines(PlayerTableFormatter.csv_header())
        for player in team.players:
            csv.writelines(PlayerTableFormatter.csv(player))


def main():
    """Main function."""
    create_team()


if __name__ == "__main__":
    main()
