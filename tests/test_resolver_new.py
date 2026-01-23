"""
Unit tests for the Resolver class.

Tests cover:
- Pitch outcome determination
- Ball/strike handling
- Walk resolution (regular, HBP, IBB, catcher interference)
- Hit resolution (singles, doubles, triples, home runs)
- Out resolution (fly outs, ground outs, strikeouts)
- Special plays (double plays, triple plays, fielder's choice, sacrifice flies/bunts)
- Foul balls
- Edge cases and validation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.game.resolver import Resolver
from src.game.intents.pitch import PitchIntent
from src.game.events.ball import BallEvent, IllegalPitch
from src.game.events.strike import (
    StrikeEvent,
    FoulStrikeEvent,
    FouledOffThirdStrikeEvent,
    FoulTipCaughtThirdStrikeEvent,
)
from src.game.events.strikeout import StrikeOutEvent
from src.game.events.out import OutRecordedEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.events.hbp import HitByPitchEvent
from src.game.events.hits import SingleEvent, DoubleEvent, TripleEvent, HomeRunEvent
from src.game.events.double_play import DoublePlayEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.sacrifice import SacBuntEvent, SacFlyEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.balk import BalkEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.bases import FIRST, SECOND, THIRD, HOME


class MockRNG:
    """Mock RNG for deterministic testing"""

    def __init__(self, value=0.5):
        self.value = value
        self.call_count = 0

    def random(self):
        self.call_count += 1
        return self.value

    def set_value(self, value):
        self.value = value


class MockCount:
    """Mock count object"""

    def __init__(self, balls=0, strikes=0):
        self.balls = balls
        self.strikes = strikes

    def snapshot(self):
        return {"balls": self.balls, "strikes": self.strikes}


class MockBases:
    """Mock bases object"""

    def __init__(self):
        self._runners = {}
        self.is_empty = True

    def runner_on(self, base):
        return self._runners.get(base)

    def set_runner(self, base, runner_id):
        self._runners[base] = runner_id
        self.is_empty = len(self._runners) == 0

    def clear(self):
        self._runners = {}
        self.is_empty = True

    def occupied_map(self):
        return {base: runner for base, runner in self._runners.items()}

    def is_loaded(self):
        return FIRST in self._runners and SECOND in self._runners and THIRD in self._runners


class MockGame:
    """Mock game object"""

    def __init__(self):
        self.count = MockCount()
        self.bases = MockBases()
        self.outs = 0


@pytest.fixture
def rng():
    return MockRNG()


@pytest.fixture
def resolver(rng):
    return Resolver(rng)


@pytest.fixture
def game():
    return MockGame()


@pytest.fixture
def pitch_intent():
    return PitchIntent(
        pitcher_id="pitcher_1", batter_id="batter_1", pitch_type="fastball"
    )


# ================================================================
# BASIC FUNCTIONALITY TESTS
# ================================================================


class TestBasicFunctionality:
    """Test basic resolver functionality"""

    def test_random_event_basic(self, resolver):
        """Test random event selection with simple probabilities"""
        probs = {"event_a": 50, "event_b": 50}
        resolver.rng.set_value(0.25)  # Should select first event
        result = resolver.random_event(probs)
        assert result == "event_a"

    def test_random_event_weighted(self, resolver):
        """Test random event selection with weighted probabilities"""
        probs = {"rare": 10, "common": 90}
        resolver.rng.set_value(0.95)  # Should select second event
        result = resolver.random_event(probs)
        assert result == "common"

    def test_random_event_empty_probs(self, resolver):
        """Test that empty probabilities raise ValueError"""
        with pytest.raises(ValueError):
            resolver.random_event({})

    def test_random_event_none_probs(self, resolver):
        """Test that None probabilities raise ValueError"""
        with pytest.raises(ValueError):
            resolver.random_event(None)


# ================================================================
# BALL TESTS
# ================================================================


class TestBalls:
    """Test ball outcomes"""

    def test_ball_called(self, resolver, game, pitch_intent):
        """Test a ball is properly recorded"""
        with patch.object(resolver, "_determine_pitch_outcome", return_value="ball"):
            events = resolver._resolve_pitch(pitch_intent, game)

        # Should have PitchThrown and Ball events
        assert len(events) == 2
        assert isinstance(events[1], BallEvent)

    def test_ball_walk_on_fourth_ball(self, resolver, game, pitch_intent):
        """Test that fourth ball results in a walk"""
        game.count.balls = 3  # 3 balls already

        with patch.object(resolver, "_determine_pitch_outcome", return_value="ball"):
            events = resolver._resolve_pitch(pitch_intent, game)

        # Should have walk events
        walk_event = next((e for e in events if isinstance(e, WalkEvent)), None)
        assert walk_event is not None
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )
        assert pa_end is not None

    def test_illegal_pitch(self, resolver, game, pitch_intent):
        """Test illegal pitch adds a ball"""
        with patch.object(
            resolver, "_determine_pitch_outcome", return_value="illegal_pitch"
        ):
            events = resolver._resolve_pitch(pitch_intent, game)

        # Should have IllegalPitch and Ball
        illegal_pitch = next((e for e in events if isinstance(e, IllegalPitch)), None)
        ball = next((e for e in events if isinstance(e, BallEvent)), None)
        assert illegal_pitch is not None
        assert ball is not None


# ================================================================
# STRIKE TESTS
# ================================================================


class TestStrikes:
    """Test strike outcomes"""

    def test_called_strike(self, resolver, game, pitch_intent):
        """Test called strike"""
        with patch.object(
            resolver, "_determine_pitch_outcome", return_value="called_strike"
        ):
            events = resolver._resolve_pitch(pitch_intent, game)

        strike = next((e for e in events if isinstance(e, StrikeEvent)), None)
        assert strike is not None
        assert strike.swinging is False

    def test_swinging_strike(self, resolver, game, pitch_intent):
        """Test swinging strike"""
        with patch.object(
            resolver, "_determine_pitch_outcome", return_value="swinging_strike"
        ):
            events = resolver._resolve_pitch(pitch_intent, game)

        strike = next((e for e in events if isinstance(e, StrikeEvent)), None)
        assert strike is not None
        assert strike.swinging is True

    def test_strikeout_on_third_strike(self, resolver, game, pitch_intent):
        """Test strikeout on third strike"""
        game.count.strikes = 2  # 2 strikes already

        with patch.object(resolver, "_determine_pitch_outcome", return_value="strike"):
            events = resolver._resolve_pitch(pitch_intent, game)

        # Should have strikeout, out recorded, and PA end
        strikeout = next((e for e in events if isinstance(e, StrikeOutEvent)), None)
        out_recorded = next(
            (e for e in events if isinstance(e, OutRecordedEvent)), None
        )
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )

        assert strikeout is not None
        assert out_recorded is not None
        assert pa_end is not None


# ================================================================
# FOUL BALL TESTS
# ================================================================


class TestFoulBalls:
    """Test foul ball outcomes"""

    def test_foul_with_less_than_two_strikes(self, resolver, game, pitch_intent):
        """Test foul ball with less than 2 strikes"""
        game.count.strikes = 1
        resolver.rng.set_value(0.5)  # Not a foul fly out

        with patch.object(resolver, "_determine_pitch_outcome", return_value="foul"):
            events = resolver._resolve_pitch(pitch_intent, game)

        foul_strike = next((e for e in events if isinstance(e, FoulStrikeEvent)), None)
        assert foul_strike is not None

    def test_foul_with_two_strikes_fouled_off(self, resolver, game, pitch_intent):
        """Test foul ball with 2 strikes doesn't cause strikeout"""
        game.count.strikes = 2
        resolver.rng.set_value(0.5)  # Fouled off, not caught

        with patch.object(resolver, "_determine_pitch_outcome", return_value="foul"):
            events = resolver._resolve_pitch(pitch_intent, game)

        fouled_off = next(
            (e for e in events if isinstance(e, FouledOffThirdStrikeEvent)), None
        )
        assert fouled_off is not None

        # Should NOT have strikeout
        strikeout = next((e for e in events if isinstance(e, StrikeOutEvent)), None)
        assert strikeout is None

    def test_foul_tip_caught_strikeout(self, resolver, game, pitch_intent):
        """Test foul tip caught on third strike"""
        game.count.strikes = 2
        resolver.rng.set_value(0.01)  # Foul tip caught (< 0.05)

        with patch.object(resolver, "_determine_pitch_outcome", return_value="foul"):
            events = resolver._resolve_pitch(pitch_intent, game)

        foul_tip = next(
            (e for e in events if isinstance(e, FoulTipCaughtThirdStrikeEvent)), None
        )
        strikeout = next((e for e in events if isinstance(e, StrikeOutEvent)), None)

        assert foul_tip is not None
        assert strikeout is not None

    def test_foul_fly_out(self, resolver, game, pitch_intent):
        """Test foul fly ball caught for out"""
        game.count.strikes = 1
        resolver.rng.set_value(0.01)  # Foul fly out (< 0.05)

        with patch.object(resolver, "_determine_pitch_outcome", return_value="foul"):
            events = resolver._resolve_pitch(pitch_intent, game)

        out_recorded = next(
            (e for e in events if isinstance(e, OutRecordedEvent)), None
        )
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )

        assert out_recorded is not None
        assert out_recorded.reason == "foul_fly_out"
        assert pa_end is not None


# ================================================================
# WALK TESTS
# ================================================================


class TestWalks:
    """Test walk outcomes"""

    def test_regular_walk_no_runners(self, resolver, game, pitch_intent):
        """Test walk with no runners on base"""
        events = resolver._resolve_walk(pitch_intent, game)

        walk = next((e for e in events if isinstance(e, WalkEvent)), None)
        batter_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "batter_1"
                and e.to_base == FIRST
            ),
            None,
        )
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )

        assert walk is not None
        assert batter_advance is not None
        assert pa_end is not None

    def test_walk_forces_runner_from_first(self, resolver, game, pitch_intent):
        """Test walk forces runner on first to second"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with patch("src.game.rules.force_advancement.force_advance_chain") as mock_force:
            # Mock the force advancement
            mock_force.return_value = [
                Mock(
                    runner_id="runner_1",
                    from_base=FIRST,
                    to_base=SECOND,
                    reason="walk",
                    rbi_batter_id="batter_1",
                )
            ]

            events = resolver._resolve_walk(pitch_intent, game)

        # Should have runner advancement from first to second
        runner_advances = [
            e for e in events if isinstance(e, RunnerAdvancedEvent) and e.runner_id == "runner_1"
        ]
        assert len(runner_advances) == 1
        assert runner_advances[0].to_base == SECOND

    def test_intentional_walk(self, resolver, game, pitch_intent):
        """Test intentional walk"""
        events = resolver._resolve_walk(pitch_intent, game, intentional=True)

        ibb = next((e for e in events if isinstance(e, IBBEvent)), None)
        assert ibb is not None

    def test_hit_by_pitch(self, resolver, game, pitch_intent):
        """Test hit by pitch"""
        events = resolver._resolve_walk(pitch_intent, game, hbp=True)

        hbp = next((e for e in events if isinstance(e, HitByPitchEvent)), None)
        assert hbp is not None

    def test_catcher_interference(self, resolver, game, pitch_intent):
        """Test catcher interference"""
        events = resolver._resolve_walk(pitch_intent, game, catcher_interference=True)

        ci = next(
            (e for e in events if isinstance(e, CatcherInterferenceEvent)), None
        )
        assert ci is not None


# ================================================================
# HIT TESTS
# ================================================================


class TestHits:
    """Test hit outcomes"""

    def test_single_no_runners(self, resolver, game, pitch_intent):
        """Test single with no runners on base"""
        events = resolver._resolve_single(pitch_intent, game)

        single = next((e for e in events if isinstance(e, SingleEvent)), None)
        batter_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "batter_1"
                and e.to_base == FIRST
            ),
            None,
        )
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )

        assert single is not None
        assert batter_advance is not None
        assert pa_end is not None

    def test_single_runner_on_third_scores(self, resolver, game, pitch_intent):
        """Test single scores runner from third"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_single(pitch_intent, game)

        # Runner should advance from third to home
        runner_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "runner_3"
                and e.to_base == HOME
            ),
            None,
        )
        assert runner_advance is not None
        assert runner_advance.from_base == THIRD

    def test_double_no_runners(self, resolver, game, pitch_intent):
        """Test double with no runners on base"""
        events = resolver._resolve_double(pitch_intent, game)

        double = next((e for e in events if isinstance(e, DoubleEvent)), None)
        batter_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "batter_1"
                and e.to_base == SECOND
            ),
            None,
        )

        assert double is not None
        assert batter_advance is not None

    def test_double_runner_on_second_scores(self, resolver, game, pitch_intent):
        """Test double scores runner from second"""
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.is_empty = False

        events = resolver._resolve_double(pitch_intent, game)

        # Runner should advance from second to home (2 + 2 = 4 = HOME)
        runner_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "runner_2"
                and e.to_base == HOME
            ),
            None,
        )
        assert runner_advance is not None

    def test_double_runner_on_third_doesnt_overflow(self, resolver, game, pitch_intent):
        """Test double doesn't send runner from third beyond home"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_double(pitch_intent, game)

        # Runner should advance to HOME, not base 5
        runner_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent) and e.runner_id == "runner_3"
            ),
            None,
        )
        assert runner_advance is not None
        assert runner_advance.to_base == HOME
        assert runner_advance.to_base <= HOME

    def test_triple_all_runners_score(self, resolver, game, pitch_intent):
        """Test triple scores all runners"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_triple(pitch_intent, game)

        # All runners should score
        runner_advances = [
            e
            for e in events
            if isinstance(e, RunnerAdvancedEvent)
            and e.runner_id in ["runner_1", "runner_2", "runner_3"]
        ]

        assert len(runner_advances) == 3
        for advance in runner_advances:
            assert advance.to_base == HOME

    def test_triple_batter_to_third(self, resolver, game, pitch_intent):
        """Test triple puts batter on third"""
        events = resolver._resolve_triple(pitch_intent, game)

        batter_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "batter_1"
                and e.to_base == THIRD
            ),
            None,
        )
        assert batter_advance is not None

    def test_home_run_grand_slam(self, resolver, game, pitch_intent):
        """Test home run with bases loaded (grand slam)"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_home_run(pitch_intent, game)

        home_run = next((e for e in events if isinstance(e, HomeRunEvent)), None)
        assert home_run is not None

        # All four players should score
        scores = [
            e
            for e in events
            if isinstance(e, RunnerAdvancedEvent) and e.to_base == HOME
        ]
        assert len(scores) == 4  # 3 runners + batter


# ================================================================
# OUT TESTS
# ================================================================


class TestOuts:
    """Test out outcomes"""

    def test_fly_out(self, resolver, game, pitch_intent):
        """Test fly out"""
        events = resolver._resolve_fly_out(pitch_intent, game)

        out_recorded = next(
            (e for e in events if isinstance(e, OutRecordedEvent)), None
        )
        assert out_recorded is not None
        assert out_recorded.reason == "fly_out"

    def test_ground_out(self, resolver, game, pitch_intent):
        """Test ground out"""
        events = resolver._resolve_ground_out(pitch_intent, game)

        out_recorded = next(
            (e for e in events if isinstance(e, OutRecordedEvent)), None
        )
        assert out_recorded is not None
        assert out_recorded.reason == "ground_out"


# ================================================================
# DOUBLE PLAY TESTS
# ================================================================


class TestDoublePlays:
    """Test double play outcomes"""

    def test_double_play_requires_runners(self, resolver, game, pitch_intent):
        """Test double play fails with no runners"""
        with pytest.raises(RuntimeError, match="no runners on base"):
            resolver._resolve_double_play(pitch_intent, game)

    def test_double_play_requires_less_than_two_outs(self, resolver, game, pitch_intent):
        """Test double play fails with 2 outs"""
        game.outs = 2
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="2 outs"):
            resolver._resolve_double_play(pitch_intent, game)

    def test_double_play_runner_on_first(self, resolver, game, pitch_intent):
        """Test double play with runner on first"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        events = resolver._resolve_double_play(pitch_intent, game)

        # Should have double play event and two outs
        dp = next((e for e in events if isinstance(e, DoublePlayEvent)), None)
        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        runner_removed = next(
            (e for e in events if isinstance(e, RunnerRemovedEvent)), None
        )

        assert dp is not None
        assert len(outs) == 2
        assert runner_removed is not None
        assert runner_removed.runner_id == "runner_1"

    def test_double_play_no_runner_on_first_uses_third(
        self, resolver, game, pitch_intent
    ):
        """Test double play without runner on first uses third"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_double_play(pitch_intent, game)

        runner_removed = next(
            (e for e in events if isinstance(e, RunnerRemovedEvent)), None
        )
        assert runner_removed is not None
        assert runner_removed.runner_id == "runner_3"
        assert runner_removed.from_base == THIRD

    def test_double_play_only_runner_on_second(self, resolver, game, pitch_intent):
        """Test double play with only runner on second"""
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.is_empty = False

        events = resolver._resolve_double_play(pitch_intent, game)

        runner_removed = next(
            (e for e in events if isinstance(e, RunnerRemovedEvent)), None
        )
        assert runner_removed is not None
        assert runner_removed.runner_id == "runner_2"
        assert runner_removed.from_base == SECOND


# ================================================================
# TRIPLE PLAY TESTS
# ================================================================


class TestTriplePlays:
    """Test triple play outcomes"""

    def test_triple_play_requires_zero_outs(self, resolver, game, pitch_intent):
        """Test triple play requires 0 outs"""
        game.outs = 1
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="outs already in the inning"):
            resolver._resolve_triple_play(pitch_intent, game)

    def test_triple_play_requires_two_runners(self, resolver, game, pitch_intent):
        """Test triple play requires at least 2 runners"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="at least 2 runners"):
            resolver._resolve_triple_play(pitch_intent, game)

    def test_triple_play_bases_loaded(self, resolver, game, pitch_intent):
        """Test triple play with bases loaded"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False
        resolver.rng.set_value(0.1)  # First condition

        events = resolver._resolve_triple_play(pitch_intent, game)

        tp = next((e for e in events if isinstance(e, TriplePlayEvent)), None)
        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        runner_removed = [e for e in events if isinstance(e, RunnerRemovedEvent)]

        assert tp is not None
        assert len(outs) == 3
        assert len(runner_removed) == 2  # Two runners removed

    def test_triple_play_two_runners(self, resolver, game, pitch_intent):
        """Test triple play with two runners"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.is_empty = False

        events = resolver._resolve_triple_play(pitch_intent, game)

        outs = [e for e in events if isinstance(e, OutRecordedEvent)]
        runner_removed = [e for e in events if isinstance(e, RunnerRemovedEvent)]

        assert len(outs) == 3
        assert len(runner_removed) == 2


# ================================================================
# FIELDER'S CHOICE TESTS
# ================================================================


class TestFieldersChoice:
    """Test fielder's choice outcomes"""

    def test_fielders_choice_requires_runners(self, resolver, game, pitch_intent):
        """Test fielder's choice requires runners on base"""
        with pytest.raises(RuntimeError, match="no runners on base"):
            resolver._resolve_fielders_choice(pitch_intent, game)

    def test_fielders_choice_requires_less_than_two_outs(
        self, resolver, game, pitch_intent
    ):
        """Test fielder's choice requires less than 2 outs"""
        game.outs = 2
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="2 outs"):
            resolver._resolve_fielders_choice(pitch_intent, game)

    def test_fielders_choice_runner_on_third(self, resolver, game, pitch_intent):
        """Test fielder's choice removes runner on third"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_fielders_choice(pitch_intent, game)

        fc = next((e for e in events if isinstance(e, FieldersChoiceEvent)), None)
        runner_removed = next(
            (e for e in events if isinstance(e, RunnerRemovedEvent)), None
        )
        batter_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent) and e.runner_id == "batter_1"
            ),
            None,
        )

        assert fc is not None
        assert runner_removed is not None
        assert runner_removed.runner_id == "runner_3"
        assert batter_advance is not None
        assert batter_advance.to_base == FIRST

    def test_fielders_choice_runner_on_first(self, resolver, game, pitch_intent):
        """Test fielder's choice removes runner on first"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        events = resolver._resolve_fielders_choice(pitch_intent, game)

        runner_removed = next(
            (e for e in events if isinstance(e, RunnerRemovedEvent)), None
        )
        assert runner_removed is not None
        assert runner_removed.runner_id == "runner_1"


# ================================================================
# SACRIFICE TESTS
# ================================================================


class TestSacrifices:
    """Test sacrifice outcomes"""

    def test_sac_bunt_requires_runners(self, resolver, game, pitch_intent):
        """Test sacrifice bunt requires runners"""
        with pytest.raises(RuntimeError, match="no runners on base"):
            resolver._resolve_sac_bunt(pitch_intent, game)

    def test_sac_bunt_requires_less_than_two_outs(
        self, resolver, game, pitch_intent
    ):
        """Test sacrifice bunt requires less than 2 outs"""
        game.outs = 2
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="2 outs"):
            resolver._resolve_sac_bunt(pitch_intent, game)

    def test_sac_bunt_advances_runner(self, resolver, game, pitch_intent):
        """Test sacrifice bunt advances runner"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        events = resolver._resolve_sac_bunt(pitch_intent, game)

        sac_bunt = next((e for e in events if isinstance(e, SacBuntEvent)), None)
        out = next((e for e in events if isinstance(e, OutRecordedEvent)), None)
        runner_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent) and e.runner_id == "runner_1"
            ),
            None,
        )

        assert sac_bunt is not None
        assert out is not None
        assert runner_advance is not None
        assert runner_advance.to_base == SECOND

    def test_sac_fly_requires_runner_on_third(self, resolver, game, pitch_intent):
        """Test sacrifice fly requires runner on third"""
        with pytest.raises(RuntimeError, match="runner on third"):
            resolver._resolve_sac_fly(pitch_intent, game)

    def test_sac_fly_requires_less_than_two_outs(self, resolver, game, pitch_intent):
        """Test sacrifice fly requires less than 2 outs"""
        game.outs = 2
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        with pytest.raises(RuntimeError, match="2 outs"):
            resolver._resolve_sac_fly(pitch_intent, game)

    def test_sac_fly_scores_runner_from_third(self, resolver, game, pitch_intent):
        """Test sacrifice fly scores runner from third"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._resolve_sac_fly(pitch_intent, game)

        sac_fly = next((e for e in events if isinstance(e, SacFlyEvent)), None)
        out = next((e for e in events if isinstance(e, OutRecordedEvent)), None)
        runner_advance = next(
            (
                e
                for e in events
                if isinstance(e, RunnerAdvancedEvent)
                and e.runner_id == "runner_3"
                and e.to_base == HOME
            ),
            None,
        )

        assert sac_fly is not None
        assert out is not None
        assert runner_advance is not None


# ================================================================
# SPECIAL EVENT TESTS
# ================================================================


class TestSpecialEvents:
    """Test special event outcomes"""

    def test_balk_with_runners(self, resolver, game, pitch_intent):
        """Test balk with runners on base"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with patch.object(resolver, "_determine_pitch_outcome", return_value="balk"):
            events = resolver._resolve_pitch(pitch_intent, game)

        balk = next((e for e in events if isinstance(e, BalkEvent)), None)
        assert balk is not None

    def test_balk_without_runners_ignored(self, resolver, game, pitch_intent):
        """Test balk without runners is ignored"""
        with patch.object(resolver, "_determine_pitch_outcome", return_value="balk"):
            events = resolver._resolve_pitch(pitch_intent, game)

        balk = next((e for e in events if isinstance(e, BalkEvent)), None)
        assert balk is None

    def test_wild_pitch_with_runners(self, resolver, game, pitch_intent):
        """Test wild pitch with runners"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with patch.object(
            resolver, "_determine_pitch_outcome", return_value="wild_pitch"
        ):
            events = resolver._resolve_pitch(pitch_intent, game)

        wp = next((e for e in events if isinstance(e, WildPitchEvent)), None)
        assert wp is not None

    def test_passed_ball_with_runners(self, resolver, game, pitch_intent):
        """Test passed ball with runners"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        with patch.object(
            resolver, "_determine_pitch_outcome", return_value="passed_ball"
        ):
            events = resolver._resolve_pitch(pitch_intent, game)

        pb = next((e for e in events if isinstance(e, PassedBallEvent)), None)
        assert pb is not None


# ================================================================
# VALIDATION TESTS
# ================================================================


class TestValidation:
    """Test validation helper method"""

    def test_validate_max_outs(self, resolver, game):
        """Test max_outs validation"""
        game.outs = 2
        with pytest.raises(RuntimeError, match="2 outs"):
            resolver._validate_game_state(game, max_outs=2)

    def test_validate_require_runners(self, resolver, game):
        """Test require_runners validation"""
        with pytest.raises(RuntimeError, match="no runners on base"):
            resolver._validate_game_state(game, require_runners=True)

    def test_validate_require_runner_on_base(self, resolver, game):
        """Test require_runner_on validation"""
        with pytest.raises(RuntimeError, match="runner on third"):
            resolver._validate_game_state(game, require_runner_on=THIRD)

    def test_validate_passes_with_valid_state(self, resolver, game):
        """Test validation passes with valid state"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.is_empty = False

        # Should not raise
        resolver._validate_game_state(
            game, max_outs=2, require_runners=True, require_runner_on=FIRST
        )


# ================================================================
# HELPER METHOD TESTS
# ================================================================


class TestHelperMethods:
    """Test helper methods"""

    def test_advance_all_runners_empty_bases(self, resolver, game):
        """Test advancing runners with no runners on base"""
        events = resolver._advance_all_runners(
            game, (THIRD, SECOND, FIRST), advancement=1, reason="single"
        )
        assert len(events) == 0

    def test_advance_all_runners_with_runners(self, resolver, game):
        """Test advancing runners with runners on base"""
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.is_empty = False

        events = resolver._advance_all_runners(
            game,
            (THIRD, SECOND, FIRST),
            advancement=1,
            reason="single",
            rbi_batter_id="batter_1",
        )

        assert len(events) == 2
        assert all(isinstance(e, RunnerAdvancedEvent) for e in events)

    def test_advance_all_runners_caps_at_home(self, resolver, game):
        """Test runner advancement is capped at HOME"""
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        events = resolver._advance_all_runners(
            game, (THIRD,), advancement=5, reason="test"
        )

        assert len(events) == 1
        assert events[0].to_base == HOME
        assert events[0].to_base <= HOME

    def test_advance_batter_to_base(self, resolver):
        """Test batter advancement helper"""
        event = resolver._advance_batter_to_base("batter_1", SECOND, "double")

        assert isinstance(event, RunnerAdvancedEvent)
        assert event.runner_id == "batter_1"
        assert event.from_base is None
        assert event.to_base == SECOND
        assert event.reason == "double"


# ================================================================
# INTEGRATION TESTS
# ================================================================


class TestIntegration:
    """Integration tests combining multiple components"""

    def test_full_at_bat_strikeout(self, resolver, game, pitch_intent):
        """Test full at-bat ending in strikeout"""
        # Strike 1
        game.count.strikes = 0
        with patch.object(resolver, "_determine_pitch_outcome", return_value="strike"):
            events1 = resolver._resolve_pitch(pitch_intent, game)
        game.count.strikes = 1

        # Strike 2
        with patch.object(resolver, "_determine_pitch_outcome", return_value="strike"):
            events2 = resolver._resolve_pitch(pitch_intent, game)
        game.count.strikes = 2

        # Strike 3 - strikeout
        with patch.object(resolver, "_determine_pitch_outcome", return_value="strike"):
            events3 = resolver._resolve_pitch(pitch_intent, game)

        # Final pitch should end PA
        pa_end = next(
            (e for e in events3 if isinstance(e, PlateAppearanceEndEvent)), None
        )
        assert pa_end is not None

    def test_full_at_bat_walk(self, resolver, game, pitch_intent):
        """Test full at-bat ending in walk"""
        # Ball 1-3
        for i in range(3):
            game.count.balls = i
            with patch.object(
                resolver, "_determine_pitch_outcome", return_value="ball"
            ):
                resolver._resolve_pitch(pitch_intent, game)

        # Ball 4 - walk
        game.count.balls = 3
        with patch.object(resolver, "_determine_pitch_outcome", return_value="ball"):
            events = resolver._resolve_pitch(pitch_intent, game)

        walk = next((e for e in events if isinstance(e, WalkEvent)), None)
        pa_end = next(
            (e for e in events if isinstance(e, PlateAppearanceEndEvent)), None
        )

        assert walk is not None
        assert pa_end is not None

    def test_complex_baserunning_scenario(self, resolver, game, pitch_intent):
        """Test complex scenario with multiple runners"""
        # Bases loaded
        game.bases.set_runner(FIRST, "runner_1")
        game.bases.set_runner(SECOND, "runner_2")
        game.bases.set_runner(THIRD, "runner_3")
        game.bases.is_empty = False

        # Double should score two runs
        events = resolver._resolve_double(pitch_intent, game)

        # All runners should advance 2 bases (capped at HOME)
        advances = [e for e in events if isinstance(e, RunnerAdvancedEvent)]

        # runner_3: THIRD -> HOME
        # runner_2: SECOND -> HOME
        # runner_1: FIRST -> THIRD
        # batter: None -> SECOND

        assert len(advances) == 4

        # Check specific advances
        runner_3_advance = next(
            (e for e in advances if e.runner_id == "runner_3"), None
        )
        assert runner_3_advance.to_base == HOME

        runner_2_advance = next(
            (e for e in advances if e.runner_id == "runner_2"), None
        )
        assert runner_2_advance.to_base == HOME

        runner_1_advance = next(
            (e for e in advances if e.runner_id == "runner_1"), None
        )
        assert runner_1_advance.to_base == THIRD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
