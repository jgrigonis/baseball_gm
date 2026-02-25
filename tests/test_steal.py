# tests/test_steal.py
"""
Unit tests for src/game/resolvers/steal.py
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def make_runner(speed=50, base_running=50, name="Runner"):
    runner = MagicMock()
    runner.name = name
    runner.skills = {"speed": speed, "base_running": base_running}
    return runner


def make_player(arm=50, catching=50, name="Player"):
    player = MagicMock()
    player.name = name
    player.skills = {"arm": arm, "catching": catching}
    return player


def make_rng(value=0.5):
    """Return an RNG mock whose .random() always returns *value*."""
    rng = MagicMock()
    rng.random.return_value = value
    return rng


def make_bases(**runners):
    """
    runners: keyword args like first=runner_obj, second=None, etc.
    Bases constants: FIRST=1, SECOND=2, THIRD=3, HOME=4
    """
    mapping = {1: runners.get("first"), 2: runners.get("second"),
               3: runners.get("third"), 4: runners.get("home")}

    bases = MagicMock()
    bases.runner_on.side_effect = lambda base: mapping.get(base)
    return bases


def make_game(bases, rng=None, catcher=None, ss=None, second_b=None,
              third_b=None, pitcher=None):
    if catcher is None:
        catcher = make_player()
    if ss is None:
        ss = make_player()
    if second_b is None:
        second_b = make_player()
    if third_b is None:
        third_b = make_player()
    if pitcher is None:
        pitcher = make_player()

    pos_map = {
        "c": catcher, "ss": ss, "2b": second_b,
        "3b": third_b, "p": pitcher,
    }

    game = MagicMock()
    game.bases = bases
    game.rng = rng or make_rng()
    game.pos.side_effect = lambda p: pos_map[p]
    return game


def make_resolver(rng=None):
    resolver = MagicMock()
    resolver.rng = rng or make_rng()
    resolver.logger = MagicMock()
    return resolver


def make_intent(pitcher=None):
    intent = MagicMock()
    intent.pitcher = pitcher or make_player(name="Pitcher")
    return intent


# Import the module under test (adjust path if your PYTHONPATH differs)
from src.game.resolvers.steal import (
    adjust_steal_prob,
    resolve_steal_attempt,
    resolve_double_steal,
)
from src.game.bases import FIRST, SECOND, THIRD, HOME


# ---------------------------------------------------------------------------
# adjust_steal_prob
# ---------------------------------------------------------------------------

class TestAdjustStealProb:
    def test_all_average_returns_base_prob(self):
        """With all skills at 50 the multiplier is (50+50)/(50+50) == 1.0."""
        resolver = make_resolver()
        result = adjust_steal_prob(resolver, prob=0.70)
        assert pytest.approx(result, rel=1e-6) == 0.70

    def test_fast_runner_increases_prob(self):
        resolver = make_resolver()
        result = adjust_steal_prob(resolver, prob=0.70, run_speed=80, base_running=80,
                                   catcher_arm=50, catching_skill=50)
        assert result > 0.70

    def test_strong_catcher_decreases_prob(self):
        resolver = make_resolver()
        result = adjust_steal_prob(resolver, prob=0.70, run_speed=50, base_running=50,
                                   catcher_arm=80, catching_skill=80)
        assert result < 0.70

    def test_zero_denominator_guard(self):
        """catcher_arm + catching_skill == 0 should not raise ZeroDivisionError."""
        resolver = make_resolver()
        result = adjust_steal_prob(resolver, prob=0.70, catcher_arm=0, catching_skill=0)
        assert result > 0  # max(1, 0) guard prevents division by zero


# ---------------------------------------------------------------------------
# resolve_steal_attempt – single steal
# ---------------------------------------------------------------------------

class TestResolveStealAttempt:
    def _setup(self, rng_value, from_base=FIRST):
        runner = make_runner(speed=50, base_running=50)
        bases = make_bases(first=runner) if from_base == FIRST else make_bases(second=runner)
        rng = make_rng(rng_value)
        game = make_game(bases=bases, rng=rng)
        resolver = make_resolver(rng=rng)
        intent = make_intent()
        return resolver, game, intent, runner, from_base

    def test_no_runner_returns_empty(self):
        bases = make_bases()  # no runners
        game = make_game(bases=bases)
        resolver = make_resolver()
        events = resolve_steal_attempt(resolver, FIRST, make_intent(), game)
        assert events == []

    def test_successful_steal_emits_stolen_base_event(self):
        from src.game.events.steal import StealAttemptEvent, StolenBaseEvent
        from src.game.events.runners import RunnerAdvancedEvent

        # rng < success_prob → success
        resolver, game, intent, runner, from_base = self._setup(rng_value=0.0)
        events = resolve_steal_attempt(resolver, from_base, intent, game)

        event_types = [type(e) for e in events]
        assert StealAttemptEvent in event_types
        assert StolenBaseEvent in event_types
        assert RunnerAdvancedEvent in event_types

    def test_caught_stealing_emits_out_events(self):
        from src.game.events.steal import StealAttemptEvent, CaughtStealingEvent
        from src.game.events.out import OutRecordedEvent, PutOutEvent
        from src.game.events.runners import RunnerRemovedEvent

        # rng >= success_prob → caught
        resolver, game, intent, runner, from_base = self._setup(rng_value=1.0)
        events = resolve_steal_attempt(resolver, from_base, intent, game)

        event_types = [type(e) for e in events]
        assert CaughtStealingEvent in event_types
        assert OutRecordedEvent in event_types
        assert PutOutEvent in event_types
        assert RunnerRemovedEvent in event_types

    def test_steal_second_putout_ss_or_2b(self):
        """When caught stealing second, either SS or 2B records the out."""
        from src.game.events.out import PutOutEvent

        runner = make_runner()
        bases = make_bases(first=runner)
        ss = make_player(name="SS")
        second_b = make_player(name="2B")

        # Force SS path (rng returns 0.0 for success check AND 0.0 for SS_OVER_2B)
        rng = MagicMock()
        rng.random.side_effect = [1.0, 0.0]   # caught, then SS chosen
        game = make_game(bases=bases, rng=rng, ss=ss, second_b=second_b)
        resolver = make_resolver(rng=rng)

        events = resolve_steal_attempt(resolver, FIRST, make_intent(), game)
        put_out = next(e for e in events if isinstance(e, PutOutEvent))
        assert put_out.fielder == ss

    def test_steal_home_uses_pitcher_as_fielder(self):
        """Steal of home: catcher is fielder, pitcher is assist."""
        from src.game.events.out import PutOutEvent

        runner = make_runner()
        bases = make_bases(third=runner)
        pitcher = make_player(name="Pitcher")
        catcher = make_player(name="Catcher")
        rng = make_rng(1.0)  # caught
        game = make_game(bases=bases, rng=rng, catcher=catcher, pitcher=pitcher)
        resolver = make_resolver(rng=rng)

        events = resolve_steal_attempt(resolver, THIRD, make_intent(pitcher), game)
        put_out = next(e for e in events if isinstance(e, PutOutEvent))
        assert put_out.fielder == catcher
        assert put_out.assist == pitcher


# ---------------------------------------------------------------------------
# resolve_double_steal
# ---------------------------------------------------------------------------

class TestResolveDoubleSteal:
    """Smoke tests for the standard double steal (1st & 2nd)."""

    def _make_standard_double_steal_game(self, rng_value=None):
        runner1 = make_runner(speed=50, base_running=50, name="R1")
        runner2 = make_runner(speed=50, base_running=50, name="R2")
        bases = make_bases(first=runner1, second=runner2)
        rng = rng_value if isinstance(rng_value, MagicMock) else make_rng(rng_value or 0.5)
        game = make_game(bases=bases, rng=rng)
        return game, rng, [FIRST, SECOND]

    def test_both_safe_generates_stolen_base_events(self):
        from src.game.events.steal import StolenBaseEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng, from_bases = self._make_standard_double_steal_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="both_safe"):
            events = resolve_double_steal(resolver, from_bases, make_intent(), game)

        stolen = [e for e in events if isinstance(e, StolenBaseEvent)]
        assert len(stolen) == 2

    def test_lead_out_trail_safe(self):
        from src.game.events.steal import StolenBaseEvent, CaughtStealingEvent
        from src.game.events.out import OutRecordedEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng, from_bases = self._make_standard_double_steal_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="lead_out_trail_safe"):
            events = resolve_double_steal(resolver, from_bases, make_intent(), game)

        assert any(isinstance(e, CaughtStealingEvent) for e in events)
        assert any(isinstance(e, StolenBaseEvent) for e in events)
        assert any(isinstance(e, OutRecordedEvent) for e in events)

    def test_both_out_generates_two_outs(self):
        from src.game.events.out import OutRecordedEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng, from_bases = self._make_standard_double_steal_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="both_out"):
            events = resolve_double_steal(resolver, from_bases, make_intent(), game)

        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        assert len(outs) == 2


class TestFirstAndThirdDoubleSteal:
    def _make_game(self):
        runner1 = make_runner(speed=60, base_running=60, name="R1")
        runner3 = make_runner(speed=55, base_running=55, name="R3")
        bases = make_bases(first=runner1, third=runner3)
        rng = make_rng(0.5)
        game = make_game(bases=bases, rng=rng)
        return game, rng

    def test_both_safe_scenario(self):
        from src.game.events.steal import StolenBaseEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="both_safe"):
            events = resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)

        stolen = [e for e in events if isinstance(e, StolenBaseEvent)]
        assert len(stolen) == 2

    def test_first_advances_only(self):
        from src.game.events.steal import StolenBaseEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="first_advances_only"):
            events = resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)

        stolen = [e for e in events if isinstance(e, StolenBaseEvent)]
        assert len(stolen) == 1
        assert stolen[0].from_base == FIRST

    def test_first_out_third_scores(self):
        from src.game.events.steal import StolenBaseEvent, CaughtStealingEvent
        from src.game.events.out import OutRecordedEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="first_out_third_scores"):
            events = resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)

        # Runner on 1st caught, runner on 3rd scores
        caught = [e for e in events if isinstance(e, CaughtStealingEvent)]
        stolen = [e for e in events if isinstance(e, StolenBaseEvent)]
        assert len(caught) == 1
        assert caught[0].from_base == FIRST
        assert len(stolen) == 1
        assert stolen[0].from_base == THIRD

    def test_third_out_first_advances(self):
        from src.game.events.steal import StolenBaseEvent, CaughtStealingEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="third_out_first_advances"):
            events = resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)

        caught = [e for e in events if isinstance(e, CaughtStealingEvent)]
        stolen = [e for e in events if isinstance(e, StolenBaseEvent)]
        assert caught[0].from_base == THIRD
        assert stolen[0].from_base == FIRST

    def test_both_out_scenario(self):
        from src.game.events.out import OutRecordedEvent
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="both_out"):
            events = resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)

        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        assert len(outs) == 2

    def test_unknown_result_raises(self):
        from src.util.weighted_choice import WeightedChoice

        game, rng = self._make_game()
        resolver = make_resolver(rng=rng)

        with patch.object(WeightedChoice, "choose", return_value="bogus_result"):
            with pytest.raises(RuntimeError):
                resolve_double_steal(resolver, [FIRST, THIRD], make_intent(), game)