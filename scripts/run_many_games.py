"""
Run many games.

"""

import argparse

from src.game.event import Event
from src.game.main import Game
from src.team.team import Team


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", 
        help="Set the debug flag."
    )
    parser.add_argument(
        "--pauses",
        "-p",
        action="store_true",
        help="Set the pauses flag. Implies debug.",
    )
    parser.add_argument(
        "--innings", "-i", type=int, default=9, 
        help="Set the number of innings."
    )
    parser.add_argument(
        "--games", "-g", type=int, default=2, 
        help="Set the number of games to run."
    )
    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()
    home_wins = 0
    away_wins = 0
    for _ in range(args.games):
        home_team = Team("Team", "1")
        home_team.load_team(path="Team1.csv")
        print("Home Team prioritized")
        home_team.set_lineup(style="prioritized")
        home_team.display_lineup()

        print("Home Team auto")
        home_team.set_lineup("auto")
        home_team.display_lineup()

        print("Home Team defensive")
        home_team.set_lineup("defensive")
        home_team.display_lineup()

        print("Home Team offensive")
        home_team.set_lineup("offensive")
        home_team.display_lineup()

        print("Away Team")
        away_team = Team("Team", "40s")
        away_team.load_team(path="Team40s.csv")
        away_team.set_lineup(style="prioritized")
        away_team.display_lineup()

        my_game = Game(home_team, away_team, args.debug, args.pauses, args.innings)
        my_event = Event(my_game, args.debug)

        while my_game.game_over is False:
            my_event.do_event()

        print("Home:    " + str(my_game.score.home))
        print("Visitor: " + str(my_game.score.away))
        print("-" * 20)
        
        if my_game.winner == my_game.home:
            home_wins += 1
        if my_game.winner == my_game.away:
            away_wins += 1
    print("Home wins:" + str(home_wins))
    print("Away wins:" + str(away_wins))


if __name__ == "__main__":
    main()
