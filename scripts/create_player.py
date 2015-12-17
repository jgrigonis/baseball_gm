"""Create a player."""
from player.player import Player
from name_generator.names import NameGenerator


def main():
    debug = True
    ng = NameGenerator()
    my_player = Player(ng.first(), ng.last())
    my_player.generate()
    my_player.rate_player()
    if debug:
        print(my_player)
    print(my_player.header())
    print(my_player.horizontal())

if __name__ == "__main__":
    main()
