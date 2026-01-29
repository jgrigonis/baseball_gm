# scripts/create_nine.py

"""
Create a team of 9 players.
1 of each position

This will also write out a csv file called TeamNine.csv that represents the
team and has all its ratings.

"""

from src.player.player_formatters import PlayerTableFormatter
from src.team.team_factory import TeamFactory
from src.team.team_in_game_factory import TeamInGameFactory

# from src.util.locations import TEAM_FILES_DIR

__author__ = "josh"


def main():
    tf = TeamFactory()
    team_record = tf.generate_team(city="Team", mascot="Nine", size=9)

    print(PlayerTableFormatter.legend())
    print(PlayerTableFormatter.header_skills())
    for player in team_record.players:
        print(PlayerTableFormatter.hor_skills(player))

    team_in_game = TeamInGameFactory.from_record(team_record)

    # This works, you can verify the skills don't change:
    # for player in team_in_game.players:
    #     print(PlayerTableFormatter.hor_skills(player))

    print()
    print(PlayerTableFormatter.header_ratings())
    for player in team_in_game.players:
        print(PlayerTableFormatter.hor_ratings(player))


if __name__ == "__main__":
    main()
