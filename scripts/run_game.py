from src.game.event import Event
from src.game.main import Game


def main():
    debug = True
    my_game = Game()
    my_event = Event(my_game, debug)

    while my_game.game_over is False:
        my_event.do_event()

if __name__ == "__main__":
    main()
