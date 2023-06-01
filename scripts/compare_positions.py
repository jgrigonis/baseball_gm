"""
This script just creates a default player of every position type.
Useful for comparing the strengths and weaknesses of each
position.

The output is basically static, based on the way you have configured
the templates and the ratings.

The thing that will vary is the handedness and batting side of
the players

"""
from player.player import Player
from player import positions, position_name, skill_template
__author__ = 'josh'


def main():
    team = []
    for position, name in zip(positions, position_name):
        a_player = Player("a", name, position=position)
        a_player.apply_position_template()
        for skill in skill_template[position]:
            a_player.skills[skill] = skill_template[position][skill]
        for skill in a_player.skills:
            if a_player.skills[skill] == 0:
                a_player.skills[skill] = 50
        a_player.rate_player()
        team.append(a_player)
    print(Player.header())
    for player in team:
        print(player.horizontal())
    print(player.legend())

if __name__ == "__main__":
    main()
