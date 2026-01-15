# tests/game/test_events.py
import random

from src.game.event_generator import EventGenerator


def test_roll_event_deterministic():
    rng = random.Random(2)
    gen = EventGenerator(rng=rng)

    probs = {"a": 1, "b": 6}

    assert gen.roll_event(probs) == "b"
