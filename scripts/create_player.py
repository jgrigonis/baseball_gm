"""Create a randomly named player."""
from player.player import Player
from name_generator.names import NameGenerator


def create(position=None):
    ng = NameGenerator()
    my_player = Player(ng.first(), ng.last(), position=position)
    my_player.generate()
    return my_player


def main():
    debug = True
    my_player = create()
    if debug:
        print(my_player)
    print(my_player.header())
    print(my_player.horizontal())

if __name__ == "__main__":
    main()
