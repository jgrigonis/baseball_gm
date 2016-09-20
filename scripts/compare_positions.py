from player.player import Player
from player import positions, skill_template
__author__ = 'josh'


def main():
    team = []
    for position in positions:
        a_player = Player("a", position, position=position)
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

if __name__ == "__main__":
    main()
