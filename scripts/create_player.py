"""Create a player."""
from player.player import Player


def main():
    debug = True
    my_player = Player("first", "last")
    if debug:
        print(my_player)
    my_player.generate()
    if debug:
        print(my_player)

if __name__ == "__main__":
    main()
