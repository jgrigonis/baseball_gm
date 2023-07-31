"""
Show the legend for attribute abbreviations.

"""
from src.player.player import Player
__author__ = 'josh'


def main():
    player = Player("Foo", "Bar")
    print(player.legend())

if __name__ == "__main__":
    main()
