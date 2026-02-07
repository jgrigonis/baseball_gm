# tests/helpers/game_helpers.py


def drain_event_queue(game, max_steps=100):
    """Process all events in queue until empty"""
    steps = 1
    game.step()
    while game._queue:  # Changed from count check
        game.step()
        steps += 1
        if steps > max_steps:
            raise RuntimeError(
                f"Exceeded max steps ({max_steps}) - possible infinite loop"
            )
