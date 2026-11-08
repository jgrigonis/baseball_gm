# tests/game/test_analytics_aim.py
"""A team's Analytics department aims its steals and hit and runs: good
staff send runners in good spots and hold them in bad ones
(src/league/budget.py analytics_aim)."""

from random import Random
from types import SimpleNamespace

from src.game.bases import FIRST
from src.game.game import Game
from src.game.strategy import GameStrategy, _analytics_level
from src.league import budget as bg

TRIES = 20000


# Plain stand-ins instead of MagicMocks: a mock records every call made on it,
# and with TRIES calls per level that bookkeeping was nearly all of this
# file's run time.
class _Runner:
    def __init__(self, speed):
        self.skills = {"speed": speed, "base_running": 50}


class _RunnerOnFirst:
    is_empty = False
    is_loaded = False
    one_man_on = True
    two_men_on = False

    def __init__(self, speed):
        self.runner = _Runner(speed)

    def runner_on(self, base):
        return self.runner if base == FIRST else None

    def occupied_map(self):
        return {FIRST: self.runner}

    def only_occupied_base(self):
        return FIRST


def _steals(level, speed, arm):
    rng = Random(7)
    bases = _RunnerOnFirst(speed)
    count = SimpleNamespace(balls=0, strikes=0)
    score = SimpleNamespace(differential=0)
    return sum(
        GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=0,
            count=count,
            score=score,
            runner_speed=speed,
            catcher_arm=arm,
            rng=rng,
            analytics=level,
        )
        for _ in range(TRIES)
    )


def _hit_and_runs(level, contact, speed):
    rng = Random(7)
    bases = _RunnerOnFirst(speed)
    return sum(
        GameStrategy.should_hit_and_run(
            bases, 0, contact, 1, 1, rng=rng, analytics=level
        )
        for _ in range(TRIES)
    )


def test_aim_is_neutral_at_standard_and_in_an_average_spot():
    assert bg.analytics_aim(bg.STANDARD, 2.0) == 1.0
    assert all(bg.analytics_aim(lv, 1.0) == 1.0 for lv in range(5))
    assert bg.analytics_aim(4, 2.0) > 1.0 > bg.analytics_aim(0, 2.0)
    assert bg.analytics_aim(4, 0.5) < 1.0 < bg.analytics_aim(0, 0.5)
    # Spots are clamped, so no call runs away.
    assert bg.analytics_aim(4, 99) == bg.analytics_aim(4, bg.SPOT_MAX)


def test_good_analytics_sends_fast_runners_and_holds_slow_ones():
    fast = [_steals(lv, 80, 35) for lv in range(5)]
    slow = [_steals(lv, 35, 70) for lv in range(5)]
    assert fast == sorted(fast) and fast[4] > fast[0]
    assert slow == sorted(slow, reverse=True) and slow[0] > slow[4]


def test_good_analytics_picks_hit_and_run_spots():
    good = [_hit_and_runs(lv, 75, 75) for lv in range(5)]
    bad = [_hit_and_runs(lv, 30, 40) for lv in range(5)]
    assert good[4] > good[2] > good[0]
    assert bad[0] > bad[2] > bad[4]


def test_the_batting_team_s_level_is_read_from_the_game():
    from tests.game.test_facilities_injuries import _team

    rng = Random(1)
    home, away = _team(rng), _team(rng)
    game = Game(home, away, rng=Random(1), analytics_levels={away.record.id: 4})
    assert _analytics_level(game) == 4  # away bats first
    game.bat_team = home
    assert _analytics_level(game) == bg.STANDARD
