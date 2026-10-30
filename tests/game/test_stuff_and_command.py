# tests/game/test_stuff_and_command.py
"""A pitcher's stuff (strikes) and command (accuracy) next to a typical
league pitcher's: better pitchers get more strikes, fewer balls, home runs
and hits on balls in play, and a typical one changes nothing."""

from random import Random
from types import SimpleNamespace

from src.game.modifiers.in_play_modifiers import InPlayModifiers
from src.game.modifiers.pitch_modifiers import (
    CALLED,
    SWINGING,
    TYPICAL_ACCURACY,
    TYPICAL_STRIKES,
    PitchModifiers,
)
from src.game.score import Score
from src.util.weighted_choice import WeightedChoice

PITCH = {CALLED: 5750, SWINGING: 5750, "ball": 15000, "in_play": 5875, "home_run": 280}
IN_PLAY = {
    "fly_out": 4440,
    "ground_out": 1740,
    "single": 1320,
    "double": 372,
    "triple": 51,
}


def _pitch_weights(strikes, accuracy):
    resolver = SimpleNamespace(pitch_outcome=WeightedChoice(dict(PITCH), Random(1)))
    PitchModifiers.modify_for_stuff_and_command(resolver, strikes, accuracy)
    return resolver.pitch_outcome.get_weights()


def _in_play_weights(strikes, accuracy):
    resolver = SimpleNamespace(in_play_outcome=WeightedChoice(dict(IN_PLAY), Random(1)))
    skills = {
        "strikes": strikes,
        "accuracy": accuracy,
        "ground_balls": 50,
        "clutch": 50,
    }
    pitcher = SimpleNamespace(skills=skills, get_effective_stat=lambda v: v)
    InPlayModifiers.modify_for_pitcher(resolver, pitcher, Score())
    return resolver.in_play_outcome.get_weights()


def _strikes(w):
    return w[CALLED] + w[SWINGING]


def test_a_typical_pitcher_changes_nothing():
    assert _pitch_weights(TYPICAL_STRIKES, TYPICAL_ACCURACY) == PITCH
    typical = _in_play_weights(TYPICAL_STRIKES, TYPICAL_ACCURACY)
    for hit in ("single", "double", "triple"):
        assert typical[hit] == IN_PLAY[hit]


def test_stuff_misses_bats():
    good = _pitch_weights(TYPICAL_STRIKES + 15, TYPICAL_ACCURACY)
    poor = _pitch_weights(TYPICAL_STRIKES - 15, TYPICAL_ACCURACY)
    assert _strikes(good) > _strikes(poor)
    assert good["in_play"] < poor["in_play"]


def test_command_cuts_balls_and_home_runs():
    good = _pitch_weights(TYPICAL_STRIKES, TYPICAL_ACCURACY + 15)
    poor = _pitch_weights(TYPICAL_STRIKES, TYPICAL_ACCURACY - 15)
    assert good["ball"] < poor["ball"]
    assert _strikes(good) > _strikes(poor)
    assert good["home_run"] < poor["home_run"]


def test_good_pitchers_allow_weaker_contact():
    good = _in_play_weights(TYPICAL_STRIKES + 10, TYPICAL_ACCURACY + 10)
    poor = _in_play_weights(TYPICAL_STRIKES - 10, TYPICAL_ACCURACY - 10)
    for hit in ("single", "double", "triple"):
        assert good[hit] < poor[hit]
