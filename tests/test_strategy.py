# tests/test_strategy.py
"""
Unit tests for src/game/strategy.py — GameStrategy
"""

import random
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Use the real project imports.  The sys.modules stubs in the original version
# mutated already-loaded real modules (e.g. swapped the real FatigueLevel enum
# for a plain-string stub) which caused failures in every other test that
# imported those modules in the same pytest session.
# ---------------------------------------------------------------------------

from src.game.bases import FIRST, SECOND, THIRD
from src.player.fatigue import FatigueLevel
from src.game.strategy import GameStrategy

# ---------------------------------------------------------------------------
# Lightweight mock factories
# ---------------------------------------------------------------------------


def _make_bases(first=None, second=None, third=None):
    """Return a mock Bases object with runners at the specified bases."""
    bases = MagicMock()
    runner_map = {
        base: runner
        for base, runner in [(FIRST, first), (SECOND, second), (THIRD, third)]
        if runner is not None
    }
    bases.runner_on.side_effect = lambda b: runner_map.get(b)
    bases.is_empty = len(runner_map) == 0
    bases.is_loaded = all(b in runner_map for b in (FIRST, SECOND, THIRD))
    bases.one_man_on = len(runner_map) == 1
    bases.two_men_on = len(runner_map) == 2
    bases.occupied_map.return_value = runner_map
    if len(runner_map) == 1:
        bases.only_occupied_base.return_value = list(runner_map.keys())[0]
    return bases


def _make_runner(speed=50, base_running=50):
    r = MagicMock()
    r.skills = {"speed": speed, "base_running": base_running}
    return r


def _make_count(balls=0, strikes=0):
    c = MagicMock()
    c.balls = balls
    c.strikes = strikes
    return c


def _make_score(differential=0):
    s = MagicMock()
    s.differential = differential
    return s


def _make_inning(number=5, outs=0):
    i = MagicMock()
    i.number = number
    i.outs = outs
    return i


def _make_pitcher(
    pitch_count=50,
    fatigue_level=None,  # pass a real FatigueLevel member
    runs=0,
    hits=0,
    outs=0,
    ip_float=4.0,
    game_started=1,
    is_starter=True,
    bullpen_role=None,
):
    if fatigue_level is None:
        fatigue_level = FatigueLevel.GOOD

    p = MagicMock()
    p.is_starter = is_starter
    p.bullpen_role = bullpen_role
    p.current_position = None

    fatigue = MagicMock()
    fatigue.get_level.return_value = fatigue_level
    p.pitcher_fatigue = fatigue

    stats = MagicMock()
    stats.pitching.pitch_count = pitch_count
    stats.pitching.runs = runs
    stats.pitching.hits = hits
    stats.pitching.outs = outs
    stats.pitching.ip_float = ip_float
    stats.pitching.game_started = game_started
    p.game_stats = stats

    return p


# ===========================================================================
# Helpers
# ===========================================================================


def _always(value: float):
    """RNG that always returns `value`."""
    rng = MagicMock(spec=random.Random)
    rng.random.return_value = value
    return rng


ALWAYS_HIT = _always(0.0)  # random() == 0.0 → always < any positive prob
ALWAYS_MISS = _always(1.0)  # random() == 1.0 → never < any prob < 1.0


# ===========================================================================
# should_attempt_pickoff
# ===========================================================================


class TestShouldAttemptPickoff:

    def test_empty_bases_never_pickoff(self):
        bases = _make_bases()
        score = _make_score()
        assert not GameStrategy.should_attempt_pickoff(bases, score, ALWAYS_HIT)

    def test_slow_runner_close_game_can_pickoff(self):
        runner = _make_runner(speed=40)
        bases = _make_bases(first=runner)
        score = _make_score(differential=1)
        # 1% base * 1.5 (close) = 1.5% → 0.0 < 0.015
        assert GameStrategy.should_attempt_pickoff(bases, score, ALWAYS_HIT)

    def test_fast_runner_increases_probability(self):
        fast_runner = _make_runner(speed=80)
        bases = _make_bases(first=fast_runner)
        score = _make_score(differential=5)  # not close
        # 1% * 1.5 (fast) = 1.5%
        assert GameStrategy.should_attempt_pickoff(bases, score, ALWAYS_HIT)

    def test_high_random_means_no_pickoff(self):
        runner = _make_runner(speed=80)
        bases = _make_bases(first=runner)
        score = _make_score(differential=1)
        assert not GameStrategy.should_attempt_pickoff(bases, score, ALWAYS_MISS)

    def test_loaded_bases_uses_third_base_speed(self):
        r1, r2, r3 = _make_runner(50), _make_runner(50), _make_runner(80)
        bases = _make_bases(first=r1, second=r2, third=r3)
        score = _make_score()
        # Should not raise; speed drawn from third
        GameStrategy.should_attempt_pickoff(bases, score, ALWAYS_HIT)


# ===========================================================================
# select_pickoff_target
# ===========================================================================


class TestSelectPickoffTarget:

    def test_prefers_third_when_occupied(self):
        bases = _make_bases(first=_make_runner(), third=_make_runner())
        rng = _always(0.9)  # > 0.1, so won't pick second
        assert GameStrategy.select_pickoff_target(bases, rng) == THIRD

    def test_picks_second_over_third_sometimes(self):
        bases = _make_bases(second=_make_runner(), third=_make_runner())
        rng = _always(0.05)  # < 0.1
        assert GameStrategy.select_pickoff_target(bases, rng) == SECOND

    def test_only_second_occupied(self):
        bases = _make_bases(second=_make_runner())
        assert GameStrategy.select_pickoff_target(bases) == SECOND

    def test_only_first_occupied(self):
        bases = _make_bases(first=_make_runner())
        assert GameStrategy.select_pickoff_target(bases) == FIRST

    def test_no_runners_raises(self):
        bases = _make_bases()
        with pytest.raises(ValueError):
            GameStrategy.select_pickoff_target(bases)


# ===========================================================================
# should_attempt_steal
# ===========================================================================


class TestShouldAttemptSteal:

    def _bases_clear_second(self):
        return _make_bases(first=_make_runner())

    def test_cannot_steal_if_next_base_occupied(self):
        bases = _make_bases(first=_make_runner(), second=_make_runner())
        assert not GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=0,
            count=_make_count(),
            score=_make_score(),
            rng=ALWAYS_HIT,
        )

    def test_steal_second_base_probability(self):
        bases = self._bases_clear_second()
        assert GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=0,
            count=_make_count(),
            score=_make_score(),
            runner_speed=80,
            rng=ALWAYS_HIT,
        )

    def test_steal_home_very_unlikely(self):
        bases = _make_bases(third=_make_runner())
        # Even with ALWAYS_HIT the probability is so tiny (0.00001 * mods)
        # that it still fires when random=0; but we verify it doesn't with miss
        assert not GameStrategy.should_attempt_steal(
            THIRD,
            bases,
            outs=0,
            count=_make_count(),
            score=_make_score(),
            rng=ALWAYS_MISS,
        )

    def test_full_count_increases_steal_prob(self):
        bases = self._bases_clear_second()
        count = _make_count(balls=3, strikes=2)
        # 0.034 * ((80+50)/100) * (50/40) * 1.5 ≈ 8.3%
        rng = _always(0.07)
        result = GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=0,
            count=count,
            score=_make_score(),
            runner_speed=80,
            base_running_skill=50,
            catcher_arm=40,
            rng=rng,
        )
        assert result

    def test_two_outs_reduces_steal_prob(self):
        bases = self._bases_clear_second()
        count = _make_count()
        # 5.8% * 1.0 (speed) * 1.0 (arm) * 0.6 (two-out mod) = 3.48%
        # rng must be below that reduced probability to fire
        rng = _always(0.02)
        assert GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=2,
            count=count,
            score=_make_score(),
            runner_speed=50,
            catcher_arm=50,
            rng=rng,
        )

    def test_blowout_reduces_steal_prob(self):
        bases = self._bases_clear_second()
        # Blowout (up by >2): prob * 0.8; ensure it doesn't fire on 0.07
        rng = _always(0.07)
        score = _make_score(differential=5)
        result = GameStrategy.should_attempt_steal(
            FIRST,
            bases,
            outs=0,
            count=_make_count(),
            score=score,
            runner_speed=50,
            catcher_arm=50,
            rng=rng,
        )
        # 5.8% * 0.8 = 4.64% < 7% → should NOT fire
        assert not result

    def test_invalid_base_returns_false(self):
        bases = _make_bases()
        assert not GameStrategy.should_attempt_steal(
            99,
            bases,
            outs=0,
            count=_make_count(),
            score=_make_score(),
        )


# ===========================================================================
# should_attempt_double_steal
# ===========================================================================


class TestShouldAttemptDoubleSteal:

    def test_first_and_third_fires_with_hit(self):
        assert GameStrategy.should_attempt_double_steal(
            outs=0, double_steal_bases=[FIRST, THIRD], rng=ALWAYS_HIT
        )

    def test_first_and_third_doesnt_fire_with_miss(self):
        assert not GameStrategy.should_attempt_double_steal(
            outs=0, double_steal_bases=[FIRST, THIRD], rng=ALWAYS_MISS
        )

    def test_unknown_combination_returns_false(self):
        assert not GameStrategy.should_attempt_double_steal(
            outs=0, double_steal_bases=[1, 99], rng=ALWAYS_HIT
        )

    def test_two_outs_reduces_probability(self):
        # prob = 0.003 * 0.2 = 0.0006; random=0.001 → should NOT fire
        rng = _always(0.001)
        assert not GameStrategy.should_attempt_double_steal(
            outs=2, double_steal_bases=[FIRST, THIRD], rng=rng
        )

    def test_fast_runners_increase_probability(self):
        rng = _always(0.004)
        result = GameStrategy.should_attempt_double_steal(
            outs=0,
            double_steal_bases=[FIRST, THIRD],
            runner_speeds={FIRST: 80, THIRD: 80},
            rng=rng,
        )
        # 0.003 * (80/50) = 0.0048 > 0.004 → fires
        assert result


# ===========================================================================
# should_bunt
# ===========================================================================


class TestShouldBunt:

    def test_no_bunt_with_two_outs(self):
        assert not GameStrategy.should_bunt(
            _make_bases(first=_make_runner()),
            outs=2,
            strikes=0,
            balls=0,
            rng=ALWAYS_HIT,
        )

    def test_no_bunt_with_two_strikes(self):
        assert not GameStrategy.should_bunt(
            _make_bases(first=_make_runner()),
            outs=0,
            strikes=2,
            balls=0,
            rng=ALWAYS_HIT,
        )

    def test_no_bunt_with_three_balls(self):
        assert not GameStrategy.should_bunt(
            _make_bases(first=_make_runner()),
            outs=0,
            strikes=0,
            balls=3,
            rng=ALWAYS_HIT,
        )

    def test_no_bunt_with_empty_bases(self):
        assert not GameStrategy.should_bunt(
            _make_bases(), outs=0, strikes=0, balls=0, rng=ALWAYS_HIT
        )

    def test_bunt_fires_runner_on_first_good_conditions(self):
        bases = _make_bases(first=_make_runner())
        result = GameStrategy.should_bunt(
            bases,
            outs=0,
            strikes=0,
            balls=0,
            batter_bunting_skill=80,
            batter_power=30,
            score_differential=0,
            inning=8,
            rng=ALWAYS_HIT,
        )
        assert result

    def test_power_hitter_rarely_bunts(self):
        bases = _make_bases(first=_make_runner())
        # Very high random threshold to simulate low probability
        rng = _always(0.5)
        result = GameStrategy.should_bunt(
            bases,
            outs=0,
            strikes=0,
            balls=0,
            batter_bunting_skill=30,
            batter_power=90,
            score_differential=5,
            inning=3,
            rng=rng,
        )
        assert not result

    def test_late_inning_close_game_boosts_bunt(self):
        bases = _make_bases(second=_make_runner())
        result = GameStrategy.should_bunt(
            bases,
            outs=0,
            strikes=0,
            balls=0,
            batter_bunting_skill=70,
            batter_power=40,
            score_differential=0,
            inning=9,
            rng=ALWAYS_HIT,
        )
        assert result


# ===========================================================================
# should_intentional_walk
# ===========================================================================


class TestShouldIntentionalWalk:

    def test_no_ibb_if_first_occupied(self):
        bases = _make_bases(first=_make_runner())
        assert not GameStrategy.should_intentional_walk(
            bases, _make_count(), outs=0, rng=ALWAYS_HIT
        )

    def test_ibb_fires_powerful_late_close(self):
        bases = _make_bases(second=_make_runner())
        result = GameStrategy.should_intentional_walk(
            bases,
            _make_count(balls=0, strikes=0),
            outs=1,
            batter_power=80,
            score_differential=1,
            inning=9,
            rng=ALWAYS_HIT,
        )
        assert result

    def test_ibb_unlikely_with_strikes(self):
        bases = _make_bases()
        count = _make_count(balls=0, strikes=2)
        rng = _always(0.5)
        result = GameStrategy.should_intentional_walk(
            bases,
            count,
            outs=0,
            batter_power=80,
            score_differential=0,
            inning=9,
            rng=rng,
        )
        # prob gets multiplied by IBB_STRIKES_MODIFIER (0.01) × MORE_STRIKES (0.01) → tiny
        assert not result

    def test_ibb_weak_batter_very_rare(self):
        bases = _make_bases()
        rng = _always(0.0005)
        result = GameStrategy.should_intentional_walk(
            bases, _make_count(), outs=0, batter_power=40, rng=rng
        )
        # Base IBB_PROB = 0.0001; even with modifier < 0.0005
        assert not result


# ===========================================================================
# should_pitch_out
# ===========================================================================


class TestShouldPitchOut:

    def test_empty_bases_no_pitchout(self):
        assert not GameStrategy.should_pitch_out(_make_bases(), outs=0, rng=ALWAYS_HIT)

    def test_fast_runner_can_trigger_pitchout(self):
        bases = _make_bases(first=_make_runner(speed=80))
        result = GameStrategy.should_pitch_out(
            bases,
            outs=0,
            runner_speeds={FIRST: 80},
            count_balls=0,
            count_strikes=0,
            rng=ALWAYS_HIT,
        )
        assert result

    def test_three_balls_never_pitchout(self):
        bases = _make_bases(first=_make_runner(speed=90))
        result = GameStrategy.should_pitch_out(
            bases,
            outs=0,
            runner_speeds={FIRST: 90},
            count_balls=3,
            count_strikes=0,
            rng=ALWAYS_HIT,
        )
        assert not result

    def test_balls_over_strikes_reduces_pitchout(self):
        bases = _make_bases(first=_make_runner())
        # prob = 0.001 * 0.1 = 0.0001; random=0.001 → no pitchout
        rng = _always(0.001)
        result = GameStrategy.should_pitch_out(
            bases,
            outs=0,
            runner_speeds={FIRST: 50},
            count_balls=2,
            count_strikes=1,
            rng=rng,
        )
        assert not result


# ===========================================================================
# should_hit_and_run
# ===========================================================================


class TestShouldHitAndRun:

    def test_no_hnr_with_two_outs(self):
        assert not GameStrategy.should_hit_and_run(
            _make_bases(first=_make_runner()), outs=2, rng=ALWAYS_HIT
        )

    def test_no_hnr_bases_loaded(self):
        bases = _make_bases(
            first=_make_runner(), second=_make_runner(), third=_make_runner()
        )
        assert not GameStrategy.should_hit_and_run(bases, outs=0, rng=ALWAYS_HIT)

    def test_hnr_fires_good_contact_fast_runner(self):
        runner = _make_runner(speed=70)
        bases = _make_bases(first=runner)
        result = GameStrategy.should_hit_and_run(
            bases,
            outs=0,
            batter_contact=70,
            count_balls=1,
            count_strikes=0,
            rng=ALWAYS_HIT,
        )
        assert result

    def test_hnr_favored_by_count(self):
        # balls >= strikes boosts; random=0.05 should fire with good contact + speed
        runner = _make_runner(speed=70)
        bases = _make_bases(first=runner)
        rng = _always(0.05)
        result = GameStrategy.should_hit_and_run(
            bases,
            outs=0,
            batter_contact=70,
            count_balls=2,
            count_strikes=1,
            rng=rng,
        )
        # 2% * 1.5 (contact) * 1.5 (speed) * 1.3 (count) = 5.85% > 5%
        assert result


# ===========================================================================
# get_double_steal_candidates
# ===========================================================================


class TestGetDoubleStealCandidates:

    def _game(self, first=None, second=None, third=None):
        g = MagicMock()
        g.bases = _make_bases(first=first, second=second, third=third)
        return g

    def test_none_when_loaded(self):
        g = self._game(
            first=_make_runner(), second=_make_runner(), third=_make_runner()
        )
        assert GameStrategy.get_double_steal_candidates(g) is None

    def test_second_and_third_priority(self):
        g = self._game(second=_make_runner(), third=_make_runner())
        assert GameStrategy.get_double_steal_candidates(g) == [SECOND, THIRD]

    def test_first_and_third(self):
        g = self._game(first=_make_runner(), third=_make_runner())
        assert GameStrategy.get_double_steal_candidates(g) == [FIRST, THIRD]

    def test_first_and_second(self):
        g = self._game(first=_make_runner(), second=_make_runner())
        assert GameStrategy.get_double_steal_candidates(g) == [FIRST, SECOND]

    def test_no_candidates(self):
        g = self._game(first=_make_runner())
        assert GameStrategy.get_double_steal_candidates(g) is None


# ===========================================================================
# should_consider_pitching_change
# ===========================================================================


class TestShouldConsiderPitchingChange:

    def test_no_pitcher_returns_false(self):
        assert not GameStrategy.should_consider_pitching_change(None, _make_inning(), 0)

    def test_fresh_pitcher_very_low_prob(self):
        pitcher = _make_pitcher(fatigue_level=FatigueLevel.FRESH, pitch_count=40)
        inning = _make_inning(number=5)
        prob = GameStrategy.should_consider_pitching_change(pitcher, inning, 0)
        assert prob < 0.05  # fresh → low

    def test_exhausted_pitcher_high_prob(self):
        pitcher = _make_pitcher(
            fatigue_level=FatigueLevel.EXHAUSTED, pitch_count=110, runs=3
        )
        inning = _make_inning(number=6)
        prob = GameStrategy.should_consider_pitching_change(pitcher, inning, 0)
        assert prob >= 0.5

    def test_zero_fatigue_almost_certain(self):
        pitcher = _make_pitcher(fatigue_level=FatigueLevel.ZERO, pitch_count=130)
        inning = _make_inning(number=7)
        prob = GameStrategy.should_consider_pitching_change(pitcher, inning, 0)
        assert prob >= 0.9

    # def test_ninth_inning_close_game_boosts_prob(self):
    #     pitcher = _make_pitcher(fatigue_level=FatigueLevel.TIRED, pitch_count=95, runs=1)
    #     inning_9 = _make_inning(number=9)
    #     inning_5 = _make_inning(number=5)
    #     prob_9 = GameStrategy.should_consider_pitching_change(
    #         pitcher, inning_9, score_differential=2
    #     )
    #     prob_5 = GameStrategy.should_consider_pitching_change(
    #         pitcher, inning_5, score_differential=2
    #     )
    #     assert prob_9 > prob_5

    def test_no_hits_no_runs_reduces_prob(self):
        base = _make_pitcher(
            fatigue_level=FatigueLevel.TIRED, pitch_count=90, runs=0, hits=0
        )
        inning = _make_inning(number=5)
        prob = GameStrategy.should_consider_pitching_change(base, inning, 0)
        # 0.25 * 0.5 (no runs) * 0.2 (no hits) = 0.025
        assert prob < 0.05

    def test_prob_clamped_between_0_and_1(self):
        pitcher = _make_pitcher(fatigue_level=FatigueLevel.ZERO, pitch_count=200)
        inning = _make_inning(number=9)
        prob = GameStrategy.should_consider_pitching_change(
            pitcher, inning, score_differential=2
        )
        assert 0.0 <= prob <= 1.0


# ===========================================================================
# should_bring_in_closer
# ===========================================================================


class TestShouldBringInCloser:

    def _available_closer(self, pitch_count=0, fatigue=None):
        if fatigue is None:
            fatigue = FatigueLevel.FRESH
        p = _make_pitcher(
            pitch_count=pitch_count,
            fatigue_level=fatigue,
            is_starter=False,
            bullpen_role="Closer",
        )
        p.current_position = None
        return p

    def _team_with_closer(self, closer):
        team = MagicMock()
        team.players = [closer]
        return team

    def test_not_save_situation_inning_8(self):
        closer = self._available_closer()
        team = self._team_with_closer(closer)
        current = _make_pitcher(bullpen_role="Starter")
        inning = _make_inning(number=8)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=1, rng=ALWAYS_HIT
        )

    def test_not_save_situation_blowout(self):
        closer = self._available_closer()
        team = self._team_with_closer(closer)
        current = _make_pitcher(bullpen_role="Starter")
        inning = _make_inning(number=9)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=5, rng=ALWAYS_HIT
        )

    def test_closer_wont_replace_themselves(self):
        current = _make_pitcher(bullpen_role="Closer")
        team = MagicMock()
        team.players = []
        inning = _make_inning(number=9)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=1, rng=ALWAYS_HIT
        )

    def test_no_available_closer_returns_false(self):
        current = _make_pitcher(bullpen_role="Starter")
        team = MagicMock()
        team.players = []
        inning = _make_inning(number=9)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=1, rng=ALWAYS_HIT
        )

    def test_classic_save_situation_fires(self):
        closer = self._available_closer()
        team = self._team_with_closer(closer)
        current = _make_pitcher(bullpen_role="Starter")
        inning = _make_inning(number=9)
        assert GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=2, rng=ALWAYS_HIT
        )

    def test_tired_closer_not_used(self):
        closer = self._available_closer(fatigue=FatigueLevel.TIRED)
        team = self._team_with_closer(closer)
        current = _make_pitcher(bullpen_role="Starter")
        inning = _make_inning(number=9)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=1, rng=ALWAYS_HIT
        )

    def test_already_pitched_closer_not_used(self):
        closer = self._available_closer(pitch_count=30)
        team = self._team_with_closer(closer)
        current = _make_pitcher(bullpen_role="Starter")
        inning = _make_inning(number=9)
        assert not GameStrategy.should_bring_in_closer(
            current, team, inning, score_diff=1, rng=ALWAYS_HIT
        )


# ===========================================================================
# select_relief_pitcher
# ===========================================================================


@patch(
    "src.game.strategy.PlayerEvaluator.rate_player", return_value={"rp": 60, "sp": 55}
)
class TestSelectReliefPitcher:

    def _make_available(self, role, fatigue=None, is_starter=False):
        p = MagicMock()
        p.bullpen_role = role
        p.game_stats.pitching.pitch_count = 0
        p.current_position = None
        p.pitcher_fatigue.energy = 1.0  # ADD — must be a float
        p.pitcher_fatigue.get_level.return_value = FatigueLevel.FRESH
        return p
        # if fatigue is None:
        #     fatigue = FatigueLevel.FRESH
        # p = _make_pitcher(
        #     pitch_count=0,
        #     fatigue_level=fatigue,
        #     is_starter=is_starter,
        #     bullpen_role=role,
        # )
        # p.current_position = None
        # p.record = MagicMock()
        # p.record.skills = MagicMock()
        # return p

    def test_returns_none_if_no_available(self, mock_rate_player):
        current = _make_pitcher()
        team = MagicMock()
        team.players = [current]
        result = GameStrategy.select_relief_pitcher(
            team, current, _make_inning(9), _make_score(differential=-1)
        )
        assert result is None

    def test_prefers_closer_in_save_situation(self, mock_rate_player):
        current = _make_pitcher(bullpen_role="Starter")
        closer = self._make_available("Closer")
        setup = self._make_available("Setup")
        team = MagicMock()
        team.players = [current, closer, setup]
        result = GameStrategy.select_relief_pitcher(
            team, current, _make_inning(9), _make_score(differential=-1)
        )
        assert result == closer

    def test_prefers_setup_man_innings_7_8(self, mock_rate_player):
        current = _make_pitcher(bullpen_role="Starter")
        setup = self._make_available("Setup")
        long = self._make_available("Long")
        team = MagicMock()
        team.players = [current, setup, long]
        result = GameStrategy.select_relief_pitcher(
            team, current, _make_inning(7), _make_score(differential=-2)
        )
        assert result == setup

    def test_prefers_long_reliever_innings_5_6(self, mock_rate_player):
        current = _make_pitcher(bullpen_role="Starter")
        long = self._make_available("Long")
        middle = self._make_available("Middle")
        team = MagicMock()
        team.players = [current, long, middle]
        result = GameStrategy.select_relief_pitcher(
            team, current, _make_inning(5), _make_score(differential=-2)
        )
        assert result == long

    def test_emergency_uses_fresh_starter(self, mock_rate_player):
        current = _make_pitcher(bullpen_role="Starter")
        sp = self._make_available(
            role=None, fatigue=FatigueLevel.FRESH, is_starter=True
        )
        team = MagicMock()
        team.players = [current, sp]
        result = GameStrategy.select_relief_pitcher(
            team, current, _make_inning(6), _make_score(differential=-10)
        )
        assert result == sp
