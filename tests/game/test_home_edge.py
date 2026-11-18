"""Home-field edge (Josh, 2026-11-18): home hitters get a few called strikes
turned into balls and a few more hits on balls in play; road hitters get
nothing. And a clutch hitter turns outs into hits in a close game."""

from random import Random
from types import SimpleNamespace

from src.game.modifiers import in_play_modifiers as ipm
from src.game.modifiers.in_play_modifiers import InPlayModifiers
from src.game.modifiers.pitch_modifiers import (
    CALLED,
    HOME_CALLED_STRIKES,
    PitchModifiers,
    batting_at_home,
)
from src.game.score import Score
from src.util.weighted_choice import WeightedChoice

PITCH = {CALLED: 5750, "swinging_strike": 5950, "ball": 15700, "in_play": 5875}


def _game(top: bool):
    return SimpleNamespace(inning=SimpleNamespace(top=top))


def _pitch(top: bool) -> dict:
    resolver = SimpleNamespace(pitch_outcome=WeightedChoice(dict(PITCH), Random(1)))
    PitchModifiers.modify_for_home(resolver, _game(top))
    return resolver.pitch_outcome.get_weights()


def test_only_the_home_team_bats_at_home():
    assert batting_at_home(_game(top=False))
    assert not batting_at_home(_game(top=True))


def test_home_hitters_see_fewer_called_strikes():
    road, home = _pitch(top=True), _pitch(top=False)
    assert road == PITCH
    moved = PITCH[CALLED] * HOME_CALLED_STRIKES
    assert abs(PITCH[CALLED] - home[CALLED] - moved) <= 1
    assert abs(home["ball"] - PITCH["ball"] - moved) <= 1
    assert home["swinging_strike"] == PITCH["swinging_strike"]


def test_home_edge_is_small():
    assert 0 < HOME_CALLED_STRIKES < 0.05
    assert 1 < ipm.HOME_HITS < 1.1


def _batter_in_play(clutch: int) -> dict:
    weights = {"fly_out": 4440, "ground_out": 1740, "single": 1385, "double": 430, "triple": 51}
    resolver = SimpleNamespace(in_play_outcome=WeightedChoice(dict(weights), Random(1)))
    skills = {k: 50 for k in ("power", "contact", "speed", "base_running")} | {"clutch": clutch}
    batter = SimpleNamespace(skills=skills, get_effective_stat=lambda v: v)
    InPlayModifiers.modify_for_batter(resolver, batter, Score())  # tied game
    return resolver.in_play_outcome.get_weights()


def _hit_share(w: dict) -> float:
    hits = w["single"] + w["double"] + w["triple"]
    return hits / (hits + w["fly_out"] + w["ground_out"])


def test_clutch_hitter_gets_more_hits_in_a_close_game():
    assert _hit_share(_batter_in_play(75)) > _hit_share(_batter_in_play(50))
    assert _hit_share(_batter_in_play(25)) < _hit_share(_batter_in_play(50))
