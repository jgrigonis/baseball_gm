# tests/test_bases.py
import pytest

from src.game.bases import Bases, FIRST, SECOND, THIRD, HOME


class TestBasesInitialization:
    """Test initial state of Bases."""

    def test_bases_start_empty(self):
        bases = Bases()
        assert bases.runner_on(FIRST) is None
        assert bases.runner_on(SECOND) is None
        assert bases.runner_on(THIRD) is None

    def test_occupied_map_starts_empty(self):
        bases = Bases()
        assert bases.occupied_map() == {}

    def test_str_representation_empty(self):
        bases = Bases()
        assert "Empty" in str(bases)


class TestAdvanceRunner:
    """Test advancing runners."""

    def test_batter_reaches_first(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        assert bases.runner_on(FIRST) == "r1"

    def test_runner_advances_first_to_second(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r1", FIRST, SECOND)
        assert bases.runner_on(FIRST) is None
        assert bases.runner_on(SECOND) == "r1"

    def test_runner_advances_second_to_third(self):
        bases = Bases()
        bases.advance("r1", None, SECOND)
        bases.advance("r1", SECOND, THIRD)
        assert bases.runner_on(SECOND) is None
        assert bases.runner_on(THIRD) == "r1"

    def test_runner_scores_from_third(self):
        bases = Bases()
        bases.advance("r1", None, THIRD)
        bases.advance("r1", THIRD, HOME)
        assert bases.runner_on(THIRD) is None
        assert bases.base_of("r1") is None

    def test_batter_can_reach_second_double(self):
        bases = Bases()
        bases.advance("r1", None, SECOND)
        assert bases.runner_on(SECOND) == "r1"

    def test_batter_can_reach_third_triple(self):
        bases = Bases()
        bases.advance("r1", None, THIRD)
        assert bases.runner_on(THIRD) == "r1"

    def test_batter_can_score_home_run(self):
        bases = Bases()
        bases.advance("r1", None, HOME)
        assert bases.base_of("r1") is None

    def test_multiple_runners_different_bases(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)
        assert bases.runner_on(FIRST) == "r1"
        assert bases.runner_on(SECOND) == "r2"
        assert bases.runner_on(THIRD) == "r3"

    def test_occupied_map_with_runners(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, THIRD)
        occupied = bases.occupied_map()
        assert occupied == {FIRST: "r1", THIRD: "r2"}


class TestAdvanceErrors:
    """Test error conditions for advancing."""

    def test_cannot_double_occupy_base(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(RuntimeError, match="already occupied"):
            bases.advance("r2", None, FIRST)

    def test_cannot_advance_nonexistent_runner(self):
        bases = Bases()
        with pytest.raises(RuntimeError, match="not on base"):
            bases.advance("r1", FIRST, SECOND)

    def test_cannot_advance_runner_from_wrong_base(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(RuntimeError, match="not on base"):
            bases.advance("r1", SECOND, THIRD)

    def test_cannot_advance_runner_already_on_bases(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(RuntimeError, match="already on base"):
            bases.advance("r1", None, SECOND)

    def test_invalid_to_base(self):
        bases = Bases()
        with pytest.raises(ValueError, match="Invalid to_base"):
            bases.advance("r1", None, 5)

    def test_invalid_from_base(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(ValueError, match="Invalid from_base"):
            bases.advance("r1", 5, SECOND)

    def test_invalid_from_base_zero(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(ValueError, match="Invalid from_base"):
            bases.advance("r1", 0, SECOND)


class TestRemoveRunner:
    """Test removing runners from bases."""

    def test_remove_runner_from_first(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.remove("r1", FIRST)
        assert bases.runner_on(FIRST) is None

    def test_remove_runner_from_second(self):
        bases = Bases()
        bases.advance("r1", None, SECOND)
        bases.remove("r1", SECOND)
        assert bases.runner_on(SECOND) is None

    def test_remove_runner_from_third(self):
        bases = Bases()
        bases.advance("r1", None, THIRD)
        bases.remove("r1", THIRD)
        assert bases.runner_on(THIRD) is None

    def test_remove_runner_does_not_affect_others(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.remove("r1", FIRST)
        assert bases.runner_on(FIRST) is None
        assert bases.runner_on(SECOND) == "r2"

    def test_cannot_remove_nonexistent_runner(self):
        bases = Bases()
        with pytest.raises(RuntimeError, match="not on base"):
            bases.remove("r1", FIRST)

    def test_cannot_remove_runner_from_wrong_base(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        with pytest.raises(RuntimeError, match="not on base"):
            bases.remove("r1", SECOND)

    def test_remove_invalid_base(self):
        bases = Bases()
        with pytest.raises(ValueError, match="Invalid from_base"):
            bases.remove("r1", 5)


class TestQueryMethods:
    """Test query methods."""

    def test_runner_on_returns_none_when_empty(self):
        bases = Bases()
        assert bases.runner_on(FIRST) is None

    def test_runner_on_returns_runner_id(self):
        bases = Bases()
        bases.advance("r1", None, SECOND)
        assert bases.runner_on(SECOND) == "r1"

    def test_runner_on_invalid_base(self):
        bases = Bases()
        with pytest.raises(ValueError, match="Invalid base"):
            bases.runner_on(5)

    def test_runner_on_home_is_invalid(self):
        bases = Bases()
        with pytest.raises(ValueError, match="Invalid base"):
            bases.runner_on(HOME)

    def test_base_of_returns_none_when_not_on_base(self):
        bases = Bases()
        assert bases.base_of("r1") is None

    def test_base_of_returns_correct_base(self):
        bases = Bases()
        bases.advance("r1", None, SECOND)
        assert bases.base_of("r1") == SECOND

    def test_base_of_after_scoring(self):
        bases = Bases()
        bases.advance("r1", None, THIRD)
        bases.advance("r1", THIRD, HOME)
        assert bases.base_of("r1") is None

    def test_occupied_map_empty(self):
        bases = Bases()
        assert bases.occupied_map() == {}

    def test_occupied_map_single_runner(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        assert bases.occupied_map() == {FIRST: "r1"}

    def test_occupied_map_multiple_runners(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)
        assert bases.occupied_map() == {FIRST: "r1", SECOND: "r2", THIRD: "r3"}

    def test_occupied_map_is_snapshot(self):
        """Verify occupied_map returns a copy, not a reference."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        snapshot = bases.occupied_map()
        bases.advance("r1", FIRST, SECOND)
        # Snapshot should be unchanged
        assert snapshot == {FIRST: "r1"}
        assert bases.occupied_map() == {SECOND: "r1"}


class TestClear:
    """Test clearing bases."""

    def test_clear_empty_bases(self):
        bases = Bases()
        bases.clear()
        assert bases.runner_on(FIRST) is None

    def test_clear_removes_all_runners(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)
        bases.clear()
        assert bases.runner_on(FIRST) is None
        assert bases.runner_on(SECOND) is None
        assert bases.runner_on(THIRD) is None

    def test_clear_then_advance(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.clear()
        bases.advance("r2", None, FIRST)
        assert bases.runner_on(FIRST) == "r2"


class TestStringRepresentation:
    """Test string representation."""

    def test_str_empty(self):
        bases = Bases()
        s = str(bases)
        assert "Bases:" in s
        assert "Empty" in s

    def test_str_runner_on_first(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        s = str(bases)
        assert "1B=r1" in s

    def test_str_multiple_runners(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, THIRD)
        s = str(bases)
        assert "1B=r1" in s
        assert "3B=r2" in s

    def test_str_bases_loaded(self):
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)
        s = str(bases)
        assert "1B=r1" in s
        assert "2B=r2" in s
        assert "3B=r3" in s


class TestComplexScenarios:
    """Test realistic game scenarios."""

    def test_double_play_scenario(self):
        """Runner on first, ground ball double play."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        # Runner forced at second
        bases.remove("r1", FIRST)
        # Batter out at first (never reaches)
        assert bases.runner_on(FIRST) is None
        assert bases.runner_on(SECOND) is None

    def test_force_advance_at_second(self):
        """Runners on first and second, both advance."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        # New batter forces r1 to second, r2 to third
        bases.advance("r2", SECOND, THIRD)
        bases.advance("r1", FIRST, SECOND)
        bases.advance("r3", None, FIRST)
        assert bases.runner_on(FIRST) == "r3"
        assert bases.runner_on(SECOND) == "r1"
        assert bases.runner_on(THIRD) == "r2"

    def test_bases_loaded_single_scores_one(self):
        """Bases loaded, single scores runner from third."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)
        # r3 scores
        bases.advance("r3", THIRD, HOME)
        # Everyone else advances
        bases.advance("r2", SECOND, THIRD)
        bases.advance("r1", FIRST, SECOND)
        bases.advance("r4", None, FIRST)

        assert bases.base_of("r3") is None  # Scored
        assert bases.runner_on(FIRST) == "r4"
        assert bases.runner_on(SECOND) == "r1"
        assert bases.runner_on(THIRD) == "r2"

    def test_home_run_clears_all_runners(self):
        """Home run with bases loaded."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)

        # All runners score in order
        bases.advance("r3", THIRD, HOME)
        bases.advance("r2", SECOND, HOME)
        bases.advance("r1", FIRST, HOME)
        bases.advance("r4", None, HOME)  # Batter

        assert bases.occupied_map() == {}

    def test_caught_stealing_second(self):
        """Runner caught stealing second."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.remove("r1", FIRST)
        assert bases.runner_on(FIRST) is None

    def test_runner_picked_off_first(self):
        """Runner picked off first base."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.remove("r1", FIRST)
        assert bases.base_of("r1") is None

    def test_triple_play_scenario(self):
        """Bases loaded, line drive triple play."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, SECOND)
        bases.advance("r3", None, THIRD)

        # All runners removed
        bases.remove("r3", THIRD)
        bases.remove("r2", SECOND)
        bases.remove("r1", FIRST)

        assert bases.occupied_map() == {}

    def test_inning_ending_double_play(self):
        """Runners on corners, double play ends inning."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r2", None, THIRD)

        # Double play
        bases.remove("r1", FIRST)
        # Inning ends, bases cleared
        bases.clear()

        assert bases.occupied_map() == {}


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_same_runner_id_reused_after_scoring(self):
        """A runner can re-enter after scoring (new PA)."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        bases.advance("r1", FIRST, HOME)
        # Same ID can be used again
        bases.advance("r1", None, FIRST)
        assert bases.runner_on(FIRST) == "r1"

    def test_empty_string_runner_id(self):
        """Empty string is a valid (if weird) runner ID."""
        bases = Bases()
        bases.advance("", None, FIRST)
        assert bases.runner_on(FIRST) == ""

    def test_numeric_string_runner_id(self):
        """Numeric strings work as runner IDs."""
        bases = Bases()
        bases.advance("123", None, FIRST)
        assert bases.runner_on(FIRST) == "123"

    def test_very_long_runner_id(self):
        """Long runner IDs work fine."""
        bases = Bases()
        long_id = "r" * 1000
        bases.advance(long_id, None, FIRST)
        assert bases.runner_on(FIRST) == long_id

    def test_advance_through_all_bases(self):
        """Runner advances through every base."""
        bases = Bases()
        bases.advance("r1", None, FIRST)
        assert bases.base_of("r1") == FIRST

        bases.advance("r1", FIRST, SECOND)
        assert bases.base_of("r1") == SECOND

        bases.advance("r1", SECOND, THIRD)
        assert bases.base_of("r1") == THIRD

        bases.advance("r1", THIRD, HOME)
        assert bases.base_of("r1") is None
