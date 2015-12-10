from game.game_exceptions import GameException
from game.event import Event
from game.main import Game


def handle_event(event, game, debug=False):
    """Get and handle one event.

    We have try catch blocks around certain events so that they aren't
    invoked at the wrong time.

    :param event: one event from the game, as a string.
    :param game: the game object, with the game state.
    :param debug: a flag for setting debug on or off.
    """
    display_text = ""
    if event == 'ball':
        if game.count.balls == 3:
            display_text = "Walk"
        else:
            display_text = "Ball {0}".format(game.count.balls + 1)
        game.ball()
    elif event == 'strike':
        if game.count.strikes == 2:
            display_text = "Strike out"
        else:
            display_text = "Strike {0}".format(game.count.strikes + 1)
        game.strike()
    elif event == 'single':
        display_text = "Single"
        game.hit(1)
    elif event == 'double':
        display_text = "Double"
        game.hit(2)
    elif event == 'triple':
        display_text = "Triple"
        game.hit(3)
    elif event == 'homer':
        display_text = "Homer"
        game.hit(4)
    # TODO We need multiple cases of errors
    # errors should be able to move players anywhere, not just to first.
    elif event == 'error':
        try:
            # it's possible that first is occupied, and we'd get a
            # problem here.
            game.error(True)
            display_text = "Error"
        except GameException:
            return None
    elif event == 'fly_out':
        display_text = "Fly out"
        game.fly_out()
    elif event == 'ground_out':
        display_text = "Ground out"
        game.ground_out()
    elif event == 'hit_by_pitch':
        display_text = "Hit by pitch"
        game.hit_by_pitch()
    elif event == 'foul_ball':
        if game.count.strikes == 2:
            display_text = "Foul ball, still 2 strikes"
        else:
            display_text = "Foul ball, strike {0}".format(
                                    game.count.strikes + 1)
        game.foul_ball()
    elif event == 'balk':
        display_text = "Balk"
        game.balk()
    elif event == 'sacrifice':
        if game.inning.outs != 2:
            display_text = "Sacrifice"
            game.sacrifice()
        else:
            return None
    elif event == 'fielders_choice':
        try:
            # we only get fielders_choice if the runner was on first
            game.fielders_choice()
            display_text = "Fielder's choice"
        except GameException:
            return None
    # TODO there should be a ball or strike also
    # You can't get caught stealing without a pitch
    elif event == 'caught_stealing':
        try:
            # we only get caught_stealing if the runner was on first
            # and second is vacant
            game.caught_stealing("second")
            display_text = "Runner caught stealing second"
        except GameException:
            return None
    elif event == 'double_play':
        try:
            # we only get double_play if a runner was on first
            game.double_play()
            display_text = "Double play"
        except GameException:
            return None
    elif event == 'picked_off':
        try:
            # we only get picked_off if a runner was on first
            game.picked_off("first")
            display_text = "Runner picked off first"
        except GameException:
            return None
    # TODO there should be a ball or strike also
    # You can't steal without a pitch
    elif event == 'steal':
        try:
            # we only get steal if a runner was on first
            # and second is vacant
            game.steal("second")
            display_text = "Runner stole second"
        except GameException:
            return None
    elif event == 'triple_play':
        try:
            # we only get triple_play if at least 2 runners
            # are on base
            game.triple_play()
            display_text = "Triple play"
        except GameException:
            return None
    if display_text != "" and debug:
        print(display_text)


def main():
    debug = True
    my_game = Game()
    my_event = Event(my_game)
    while my_game.game_over is False:
        my_event.set_probs(my_game)
        if debug:
            print(my_event)
        one_event = my_event.get_event()
        handle_event(one_event, my_game, debug)

if __name__ == "__main__":
    main()
