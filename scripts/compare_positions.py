"""
This script just creates a random player of every position type.
Useful for comparing the strengths and weaknesses of each
position based on their seed position they are created with.

Not a very useful script.

"""

from src.player.player_factory import PlayerFactory
from src.player.player_in_game import PlayerInGame
from src.player.positions import POSITIONS, POSITION_NAME, SKILL_TEMPLATE
from src.player.player_formatters import PlayerTableFormatter

__author__ = "josh"


def main():
    print(PlayerTableFormatter.legend())
    players = []
    pigs = []
    pf = PlayerFactory()
    for position in POSITIONS:
        pr = pf.create(position=position)
        players.append(pr)
        pig = PlayerInGame(pr)
        pigs.append(pig)
    print(PlayerTableFormatter.header_skills())
    for pig in pigs:
        print(PlayerTableFormatter.hor_skills(pig))
    print(PlayerTableFormatter.header_ratings())
    for pig in pigs:
        print(PlayerTableFormatter.hor_ratings(pig))


if __name__ == "__main__":
    main()
