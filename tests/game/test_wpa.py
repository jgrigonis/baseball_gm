# tests/game/test_wpa.py
"""WPA and RE24: after every plate appearance the engine credits the batter
with how much it moved his team's chance of winning (and expected runs),
and the pitcher with the opposite (src/game/win_expectancy.py)."""

from random import Random

import pytest

from src.game import win_expectancy as we
from src.game.game import Game
from src.team.team_in_game_factory import TeamInGameFactory
from tests.factories.player_record_factory import make_player_record
from tests.factories.team_record_factory import make_team_record

TEAM = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "1b"] + ["sp"] * 10


def _play(seed, ghost_runner=True):
    rng = Random(seed)
    players = lambda: [make_player_record(position=p, rng=rng) for p in TEAM]
    home = TeamInGameFactory.from_record(make_team_record(players=players()))
    away = TeamInGameFactory.from_record(make_team_record(players=players()))
    game = Game(
        home, away, rng=Random(seed), injuries_enabled=False, ghost_runner=ghost_runner
    )
    home.set_lineup()
    away.set_lineup()
    game.play()
    return game, home, away


def _team_wpa(team):
    bat = sum(p.game_stats.batting.wpa for p in team.players)
    pit = sum(p.game_stats.pitching.wpa for p in team.players)
    return bat, pit


@pytest.mark.parametrize("seed", range(6))
def test_wpa_adds_up_to_the_result(seed):
    """A team's hitters and pitchers together added exactly what winning
    (about +0.5) or losing (about -0.5) took from the first pitch, and the
    two sides' numbers mirror each other."""
    game, home, away = _play(seed)
    hb, hp = _team_wpa(home)
    ab, ap = _team_wpa(away)
    start = we.home_win_prob(1, True, 0, 0, 0, ghost=True)  # about .5
    won = (1.0 if game.score.home > game.score.away else 0.0) - start
    assert hb + hp == pytest.approx(won, abs=1e-9)
    assert ab + ap == pytest.approx(-won, abs=1e-9)
    assert hb == pytest.approx(-ap, abs=1e-9)
    assert any(p.game_stats.batting.wpa for p in home.players)


def test_re24_mirrors_between_hitters_and_pitchers():
    game, home, away = _play(3)
    hb = sum(p.game_stats.batting.re24 for p in home.players)
    ap = sum(p.game_stats.pitching.re24 for p in away.players)
    assert hb == pytest.approx(-ap, abs=1e-9)


def test_win_expectancy_basics():
    assert we.home_win_prob(1, True, 0, 0, 0) == pytest.approx(0.5, abs=0.02)
    # Down one, two out, nobody on in the bottom of the 9th: long odds.
    assert we.home_win_prob(9, False, 2, 0, -1) < 0.1
    # Up three going to the bottom of the 9th's last out: nearly won.
    assert we.home_win_prob(9, True, 2, 0, 3) > 0.97
    # More runners and fewer outs mean more expected runs.
    assert we.run_expectancy(7, 0) > we.run_expectancy(0, 0) > we.run_expectancy(0, 2)
    # A lead is worth more late than early.
    assert we.home_win_prob(8, True, 0, 0, 2) > we.home_win_prob(2, True, 0, 0, 2)
