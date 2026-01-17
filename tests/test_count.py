# src/tests/test_count.py
import pytest
from src.game.count import Count, CountSnapshot


class TestCountInitialization:
    """Test initial state of Count."""

    def test_count_starts_at_zero_zero(self):
        count = Count()
        assert count.balls == 0
        assert count.strikes == 0

    def test_str_representation_initial(self):
        count = Count()
        assert str(count) == "0-0"


class TestAddBall:
    """Test adding balls."""

    def test_add_first_ball(self):
        count = Count()
        count.add_ball()
        assert count.balls == 1
        assert count.strikes == 0

    def test_add_multiple_balls(self):
        count = Count()
        count.add_ball()
        count.add_ball()
        count.add_ball()
        assert count.balls == 3

    def test_add_ball_does_not_affect_strikes(self):
        count = Count()
        count.add_strike()
        count.add_ball()
        assert count.strikes == 1

    def test_add_fourth_ball_reaches_limit(self):
        count = Count()
        for _ in range(4):
            count.add_ball()
        assert count.balls == 4

    def test_add_ball_at_limit_raises_error(self):
        """Adding a ball at 4 balls raises ValueError."""
        count = Count()
        for _ in range(4):
            count.add_ball()
        with pytest.raises(ValueError, match="Cannot add ball"):
            count.add_ball()

    def test_add_ball_beyond_limit_raises_error(self):
        """Verify attempting to go above 4 raises error."""
        count = Count()
        for _ in range(4):
            count.add_ball()
        assert count.balls == 4
        with pytest.raises(ValueError, match="Cannot add ball"):
            count.add_ball()


class TestAddStrike:
    """Test adding strikes."""

    def test_add_first_strike(self):
        count = Count()
        count.add_strike()
        assert count.strikes == 1
        assert count.balls == 0

    def test_add_multiple_strikes(self):
        count = Count()
        count.add_strike()
        count.add_strike()
        assert count.strikes == 2

    def test_add_strike_does_not_affect_balls(self):
        count = Count()
        count.add_ball()
        count.add_strike()
        assert count.balls == 1

    def test_add_third_strike_reaches_limit(self):
        count = Count()
        for _ in range(3):
            count.add_strike()
        assert count.strikes == 3

    def test_add_strike_at_limit_raises_error(self):
        """Adding a strike at 3 strikes raises ValueError."""
        count = Count()
        for _ in range(3):
            count.add_strike()
        with pytest.raises(ValueError, match="Cannot add strike"):
            count.add_strike()

    def test_add_strike_beyond_limit_raises_error(self):
        """Verify attempting to go above 3 raises error."""
        count = Count()
        for _ in range(3):
            count.add_strike()
        assert count.strikes == 3
        with pytest.raises(ValueError, match="Cannot add strike"):
            count.add_strike()


class TestCountQueries:
    """Test query properties."""

    def test_is_full_count_false_initially(self):
        count = Count()
        assert count.is_full_count is False

    def test_is_full_count_true_at_3_2(self):
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert count.is_full_count is True

    def test_is_full_count_false_at_3_1(self):
        count = Count()
        count.balls = 3
        count.strikes = 1
        assert count.is_full_count is False

    def test_is_full_count_false_at_2_2(self):
        count = Count()
        count.balls = 2
        count.strikes = 2
        assert count.is_full_count is False

    def test_is_three_balls_false_initially(self):
        count = Count()
        assert count.is_three_balls is False

    def test_is_three_balls_true_at_3_0(self):
        count = Count()
        count.balls = 3
        assert count.is_three_balls is True

    def test_is_three_balls_true_at_3_2(self):
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert count.is_three_balls is True

    def test_is_three_balls_false_at_2_0(self):
        count = Count()
        count.balls = 2
        assert count.is_three_balls is False

    def test_is_two_strikes_false_initially(self):
        count = Count()
        assert count.is_two_strikes is False

    def test_is_two_strikes_true_at_0_2(self):
        count = Count()
        count.strikes = 2
        assert count.is_two_strikes is True

    def test_is_two_strikes_true_at_3_2(self):
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert count.is_two_strikes is True

    def test_is_two_strikes_false_at_0_1(self):
        count = Count()
        count.strikes = 1
        assert count.is_two_strikes is False


class TestReset:
    """Test resetting the count."""

    def test_reset_from_zero_zero(self):
        count = Count()
        count.reset()
        assert count.balls == 0
        assert count.strikes == 0

    def test_reset_from_full_count(self):
        count = Count()
        count.balls = 3
        count.strikes = 2
        count.reset()
        assert count.balls == 0
        assert count.strikes == 0

    def test_reset_from_random_count(self):
        count = Count()
        count.balls = 2
        count.strikes = 1
        count.reset()
        assert count.balls == 0
        assert count.strikes == 0

    def test_reset_multiple_times(self):
        count = Count()
        count.balls = 3
        count.reset()
        count.strikes = 2
        count.reset()
        assert count.balls == 0
        assert count.strikes == 0


class TestStringRepresentation:
    """Test string formatting."""

    def test_str_zero_zero(self):
        count = Count()
        assert str(count) == "0-0"

    def test_str_one_zero(self):
        count = Count()
        count.add_ball()
        assert str(count) == "1-0"

    def test_str_zero_one(self):
        count = Count()
        count.add_strike()
        assert str(count) == "0-1"

    def test_str_full_count(self):
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert str(count) == "3-2"

    def test_str_three_balls(self):
        count = Count()
        count.balls = 3
        assert str(count) == "3-0"

    def test_str_two_strikes(self):
        count = Count()
        count.strikes = 2
        assert str(count) == "0-2"


class TestSnapshot:
    """Test snapshot functionality."""

    def test_snapshot_initial_state(self):
        count = Count()
        snap = count.snapshot()
        assert isinstance(snap, CountSnapshot)
        assert snap.balls == 0
        assert snap.strikes == 0

    def test_snapshot_with_count(self):
        count = Count()
        count.balls = 2
        count.strikes = 1
        snap = count.snapshot()
        assert snap.balls == 2
        assert snap.strikes == 1

    def test_snapshot_is_frozen(self):
        count = Count()
        snap = count.snapshot()
        with pytest.raises(Exception):  # FrozenInstanceError
            snap.balls = 5

    def test_snapshot_is_independent(self):
        """Changing count doesn't affect snapshot."""
        count = Count()
        count.balls = 1
        snap = count.snapshot()
        count.balls = 3
        assert snap.balls == 1

    def test_multiple_snapshots(self):
        count = Count()
        snap1 = count.snapshot()
        count.add_ball()
        snap2 = count.snapshot()
        count.add_strike()
        snap3 = count.snapshot()

        assert snap1.balls == 0 and snap1.strikes == 0
        assert snap2.balls == 1 and snap2.strikes == 0
        assert snap3.balls == 1 and snap3.strikes == 1


class TestCommonCountSequences:
    """Test realistic count progressions."""

    def test_strikeout_looking(self):
        """Three strikes, no balls."""
        count = Count()
        count.add_strike()
        count.add_strike()
        count.add_strike()
        assert str(count) == "0-3"

    def test_walk(self):
        """Four balls, no strikes."""
        count = Count()
        for _ in range(4):
            count.add_ball()
        assert str(count) == "4-0"

    def test_full_count_walk(self):
        """3-2 count, then ball 4."""
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert count.is_full_count
        count.add_ball()
        assert str(count) == "4-2"

    def test_full_count_strikeout(self):
        """3-2 count, then strike 3."""
        count = Count()
        count.balls = 3
        count.strikes = 2
        assert count.is_full_count
        count.add_strike()
        assert str(count) == "3-3"

    def test_alternating_balls_and_strikes(self):
        count = Count()
        count.add_ball()  # 1-0
        count.add_strike()  # 1-1
        count.add_ball()  # 2-1
        count.add_strike()  # 2-2
        count.add_ball()  # 3-2
        assert count.is_full_count

    def test_first_pitch_strike(self):
        count = Count()
        count.add_strike()
        assert str(count) == "0-1"

    def test_first_pitch_ball(self):
        count = Count()
        count.add_ball()
        assert str(count) == "1-0"

    def test_hitters_count_3_1(self):
        count = Count()
        count.balls = 3
        count.strikes = 1
        assert count.is_three_balls
        assert not count.is_two_strikes
        assert not count.is_full_count

    def test_pitchers_count_0_2(self):
        count = Count()
        count.strikes = 2
        assert count.is_two_strikes
        assert not count.is_three_balls


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_direct_attribute_assignment(self):
        """Count allows direct assignment (not encapsulated)."""
        count = Count()
        count.balls = 2
        count.strikes = 1
        assert count.balls == 2
        assert count.strikes == 1

    def test_direct_assignment_beyond_limits(self):
        """Current implementation allows invalid states via direct assignment."""
        count = Count()
        count.balls = 10
        count.strikes = 10
        assert count.balls == 10
        assert count.strikes == 10
        # This is probably not desired behavior, but testing current state

    def test_negative_values_via_direct_assignment(self):
        """Current implementation allows negative values."""
        count = Count()
        count.balls = -1
        count.strikes = -1
        assert count.balls == -1
        assert count.strikes == -1
        # This is probably not desired behavior

    def test_reset_after_reaching_limits(self):
        count = Count()
        for _ in range(4):
            count.add_ball()
        for _ in range(3):
            count.add_strike()
        count.reset()
        assert count.balls == 0
        assert count.strikes == 0

    def test_add_ball_then_reset_then_add_strike(self):
        count = Count()
        count.add_ball()
        count.reset()
        count.add_strike()
        assert count.balls == 0
        assert count.strikes == 1


class TestCountSnapshot:
    """Test the CountSnapshot dataclass."""

    def test_create_snapshot_directly(self):
        snap = CountSnapshot(balls=2, strikes=1)
        assert snap.balls == 2
        assert snap.strikes == 1

    def test_snapshot_equality(self):
        snap1 = CountSnapshot(balls=2, strikes=1)
        snap2 = CountSnapshot(balls=2, strikes=1)
        assert snap1 == snap2

    def test_snapshot_inequality(self):
        snap1 = CountSnapshot(balls=2, strikes=1)
        snap2 = CountSnapshot(balls=2, strikes=2)
        assert snap1 != snap2

    def test_snapshot_repr(self):
        snap = CountSnapshot(balls=3, strikes=2)
        repr_str = repr(snap)
        assert "3" in repr_str
        assert "2" in repr_str
