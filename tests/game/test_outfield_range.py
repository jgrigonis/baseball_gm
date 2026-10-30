# tests/game/test_outfield_range.py
"""Outfield range in the in-play weights: better outfielders catch more fly
balls and allow fewer hits."""

from random import Random
from types import SimpleNamespace

from src.game.modifiers.in_play_modifiers import TYPICAL_OF_RANGE, InPlayModifiers
from src.util.weighted_choice import WeightedChoice

WEIGHTS = {"fly_out": 4440, "single": 1320, "double": 372, "triple": 51}


def _weights_with_outfield(rng):
    """The in-play weights after defense with every outfielder at speed and
    outfield `rng`."""
    resolver = SimpleNamespace(in_play_outcome=WeightedChoice(dict(WEIGHTS), Random(1)))
    fielder = SimpleNamespace(skills={"speed": rng, "outfield": rng})
    game = SimpleNamespace(pos=lambda position: fielder)
    InPlayModifiers.modify_for_defense(resolver, game)
    return resolver.in_play_outcome.get_weights()


def test_better_outfielders_turn_hits_into_outs():
    poor = _weights_with_outfield(TYPICAL_OF_RANGE - 15)
    good = _weights_with_outfield(TYPICAL_OF_RANGE + 15)
    assert good["fly_out"] > poor["fly_out"]
    for hit in ("single", "double", "triple"):
        assert good[hit] < poor[hit]


def test_a_typical_outfield_plays_as_before():
    """The fix kept a typical outfield's effect, so league scoring holds."""
    typical = _weights_with_outfield(TYPICAL_OF_RANGE)
    old_factor = 50 / TYPICAL_OF_RANGE
    assert abs(typical["fly_out"] - WEIGHTS["fly_out"] * old_factor) <= 1
    assert abs(typical["single"] - WEIGHTS["single"] / old_factor) <= 1
