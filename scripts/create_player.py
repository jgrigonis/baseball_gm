"""Create a player."""
from player.player import Player
from name_generator.names import NameGenerator


def main():
    debug = True
    ng = NameGenerator()
    my_player = Player(ng.first(), ng.last())
    my_player.generate()
    if debug:
        print(my_player)

if __name__ == "__main__":
    main()
