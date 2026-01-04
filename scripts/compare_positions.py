"""
This script just creates a default player of every position type.
Useful for comparing the strengths and weaknesses of each
position.

The output is basically static, based on the way you have configured
the templates and the ratings.

The thing that will vary is the handedness and batting side of
the players

"""

from src.player.player import Player
from src.player.positions import positions, position_name, skill_template
from src.player.player_formatters import PlayerTableFormatter

__author__ = "josh"


def main():
    print(PlayerTableFormatter.legend())
    team = []
    for position, name in zip(positions, position_name):
        team.append(Player("a", name, position=position))
    for player in team:
        player.apply_position_template()
        for skill in skill_template[player.position]:
            player.skills[skill] = skill_template[player.position][skill]
        for skill in player.skills:
            if player.skills[skill] == 0:
                player.skills[skill] = 50
        player.rate_player()

    print(PlayerTableFormatter.header())
    for player in team:
        print(PlayerTableFormatter.horizontal(player))


if __name__ == "__main__":
    main()
