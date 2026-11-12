# tests/game/test_injury_rate.py
"""Game(injury_rate=...): the league's Injury rate setting scales everyone's
chance of getting hurt (league_constants.INJURY_RATES, 0.5x to 2x)."""

from random import Random

from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

SIDE = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "1b"] + ["sp"] * 8


def _team(rng):
    players = [make_player_record(position=pos, rng=rng) for pos in SIDE]
    return TeamInGameFactory.from_record(make_team_record(players=players))


def _injuries(seed, rate=1.0, mult=1.0):
    rng = Random(seed)
    home, away = _team(rng), _team(rng)
    mults = {home.record.id: mult, away.record.id: mult}
    game = Game(home, away, rng=Random(seed), injury_mults=mults, injury_rate=rate)
    home.set_lineup()
    away.set_lineup()
    game.play()
    return [(i[1], i[2], i[3]) for i in game.new_injuries]


def test_rate_zero_means_nobody_gets_hurt():
    assert not any(_injuries(seed, rate=0.0, mult=50.0) for seed in range(20))


def test_rate_multiplies_the_chance_like_facilities_do():
    # Double the rate is the same roll as double the Facilities multiplier,
    # so the same seeds give the very same injuries.
    for seed in range(20):
        assert _injuries(seed, rate=2.0, mult=5.0) == _injuries(seed, mult=10.0)


def test_higher_rate_more_injuries():
    low = sum(len(_injuries(seed, rate=0.5, mult=10.0)) for seed in range(30))
    high = sum(len(_injuries(seed, rate=2.0, mult=10.0)) for seed in range(30))
    assert high > 2 * low
