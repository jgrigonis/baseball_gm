# tests/helpers/game_helpers.py

from tests.helpers.event_recorder import EventRecorder


def drain_event_queue(game, max_steps=20):
    """Process all events in queue until empty"""
    # Process until count resets (walk completed)
    steps = 0
    with EventRecorder(game) as _:
        while game.count.balls != 0 or game.count.strikes != 0:
            game.step()
            steps += 1
            if steps > 20:
                break
