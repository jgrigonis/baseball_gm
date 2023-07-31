"""
Create a randomly named player. Give him random skills.
Determine his best position.

"""
from src.player.player import Player
from src.name_generator.names import NameGenerator


def create(position=None):
    ng = NameGenerator()
    my_player = Player(ng.first("male"), ng.last(), position=position)
    my_player.generate()
    return my_player


def main():
    debug = False
    my_player = create()
    # Print the player
    if debug:
        print(my_player)
    print(my_player.header())
    print(my_player.horizontal())

if __name__ == "__main__":
    main()
