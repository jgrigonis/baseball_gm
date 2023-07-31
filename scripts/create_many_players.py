"""
Create a bunch of players, print out the best players in each
skill category or position rating.

"""

from src.player.player import Player
from src.name_generator.names import NameGenerator
from scripts.create_player import create


def main():
    debug = False
    my_player = create()
    print(my_player.header())
    print(my_player.horizontal())
    for _ in range(40):
        my_player = create()
        # Print the player
        if debug:
            print(my_player)
        print(my_player.horizontal())

if __name__ == "__main__":
    main()
