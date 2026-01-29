# tests/helpers/game_helpers.py

from tests.helpers.event_recorder import EventRecorder


def drain_event_queue(game, max_steps=20):
    """Process all events in queue until empty"""
    # for i in range(max_steps):
    #     if not game.has_queued_events():
    #         return i  # Return number of steps taken
    #     game.step()
    # raise RuntimeError(f"Event queue not drained after {max_steps} steps")

    # Process until count resets (walk completed)
    steps = 0
    with EventRecorder(game) as _:
        while game.count.balls != 0 or game.count.strikes != 0:
            game.step()
            steps += 1
            if steps > 20:
                break
