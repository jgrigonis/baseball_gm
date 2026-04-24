# tests/test_inning.py
import pytest
from src.game.inning import Inning


class TestInningInitialization:
    """Test initial state of Inning."""

    def test_inning_starts_at_one(self):
        inning = Inning()
        assert inning.number == 1

    def test_inning_starts_at_top(self):
        inning = Inning()
        assert inning.top is True

    def test_inning_starts_with_no_outs(self):
        inning = Inning()
        assert inning.outs == 0

    def test_bottom_property_initially_false(self):
        inning = Inning()
        assert inning.bottom is False

    def test_str_representation_initial(self):
        inning = Inning()
        assert str(inning) == "Top of 1"


class TestTopBottomProperties:
    """Test top and bottom properties."""

    def test_top_is_true_initially(self):
        inning = Inning()
        assert inning.top is True
        assert inning.bottom is False

    def test_bottom_is_opposite_of_top(self):
        inning = Inning()
        inning.top = False
        assert inning.bottom is True

    def test_bottom_when_top_is_true(self):
        inning = Inning()
        inning.top = True
        assert inning.bottom is False

    def test_bottom_is_computed_property(self):
        """bottom is always the inverse of top."""
        inning = Inning()
        inning.top = True
        assert inning.bottom is False
        inning.top = False
        assert inning.bottom is True


class TestRecordOut:
    """Test recording outs."""

    def test_record_single_out(self):
        inning = Inning()
        inning.record_out()
        assert inning.outs == 1

    def test_record_multiple_outs_individually(self):
        inning = Inning()
        inning.record_out()
        inning.record_out()
        inning.record_out()
        assert inning.outs == 3

    def test_record_two_outs_at_once(self):
        inning = Inning()
        inning.record_out(2)
        assert inning.outs == 2

    def test_record_three_outs_at_once(self):
        inning = Inning()
        inning.record_out(3)
        assert inning.outs == 3

    def test_record_out_default_is_one(self):
        inning = Inning()
        inning.record_out()
        assert inning.outs == 1

    def test_record_zero_outs(self):
        inning = Inning()
        inning.record_out(0)
        assert inning.outs == 0

    def test_record_out_increments_existing(self):
        inning = Inning()
        inning.outs = 1
        inning.record_out()
        assert inning.outs == 2


class TestResetOuts:
    """Test resetting outs."""

    def test_reset_outs_from_zero(self):
        inning = Inning()
        inning.reset_outs()
        assert inning.outs == 0

    def test_reset_outs_from_one(self):
        inning = Inning()
        inning.record_out()
        inning.reset_outs()
        assert inning.outs == 0

    def test_reset_outs_from_three(self):
        inning = Inning()
        inning.record_out(3)
        inning.reset_outs()
        assert inning.outs == 0

    def test_reset_outs_multiple_times(self):
        inning = Inning()
        inning.record_out()
        inning.reset_outs()
        inning.record_out(2)
        inning.reset_outs()
        assert inning.outs == 0


class TestIncrement:
    """Test incrementing to next half-inning."""

    def test_increment_from_top_first(self):
        inning = Inning()
        inning.increment()
        assert inning.number == 1
        assert inning.top is False
        assert inning.bottom is True

    def test_increment_from_bottom_first(self):
        inning = Inning()
        inning.top = False
        inning.increment()
        assert inning.number == 2
        assert inning.top is True

    def test_increment_full_inning(self):
        """Top 1st -> Bottom 1st -> Top 2nd"""
        inning = Inning()
        assert str(inning) == "Top of 1"

        inning.increment()
        assert str(inning) == "Bottom of 1"

        inning.increment()
        assert str(inning) == "Top of 2"

    def test_increment_multiple_innings(self):
        inning = Inning()
        for _ in range(18):  # 9 full innings
            inning.increment()
        assert inning.number == 10
        assert inning.top is True

    def test_increment_resets_outs(self):
        inning = Inning()
        inning.record_out(2)
        inning.increment()
        assert inning.outs == 0

    def test_increment_through_extra_innings(self):
        inning = Inning()
        inning.number = 9
        inning.top = False
        inning.increment()
        assert inning.number == 10
        assert inning.top is True


class TestStringRepresentation:
    """Test string formatting."""

    def test_str_top_first(self):
        inning = Inning()
        assert str(inning) == "Top of 1"

    def test_str_bottom_first(self):
        inning = Inning()
        inning.top = False
        assert str(inning) == "Bottom of 1"

    def test_str_top_second(self):
        inning = Inning()
        inning.number = 2
        assert str(inning) == "Top of 2"

    def test_str_bottom_ninth(self):
        inning = Inning()
        inning.number = 9
        inning.top = False
        assert str(inning) == "Bottom of 9"

    def test_str_top_tenth(self):
        inning = Inning()
        inning.number = 10
        assert str(inning) == "Top of 10"

    def test_str_bottom_twelfth(self):
        inning = Inning()
        inning.number = 12
        inning.top = False
        assert str(inning) == "Bottom of 12"


class TestGameScenarios:
    """Test realistic game scenarios."""

    def test_complete_first_inning(self):
        """Play through top and bottom of first."""
        inning = Inning()

        # Top of 1st
        assert inning.number == 1
        assert inning.top is True
        inning.record_out(3)

        # Move to bottom
        inning.increment()
        assert inning.number == 1
        assert inning.bottom is True
        assert inning.outs == 0

        # Bottom of 1st
        inning.record_out(3)

        # Move to top of 2nd
        inning.increment()
        assert inning.number == 2
        assert inning.top is True
        assert inning.outs == 0

    def test_nine_inning_game(self):
        """Simulate a 9-inning game."""
        inning = Inning()

        for i in range(1, 10):
            # Top half
            assert inning.number == i
            assert inning.top is True
            inning.record_out(3)
            inning.increment()

            # Bottom half
            assert inning.number == i
            assert inning.bottom is True
            inning.record_out(3)

            if i < 9:
                inning.increment()

        # Game over
        assert inning.number == 9
        assert inning.bottom is True

    def test_extra_innings_game(self):
        """Simulate game going to extras."""
        inning = Inning()
        inning.number = 9
        inning.top = False

        # Bottom 9th ends tied
        inning.increment()

        # Top 10th
        assert inning.number == 10
        assert inning.top is True
        inning.record_out(3)
        inning.increment()

        # Bottom 10th
        assert inning.number == 10
        assert inning.bottom is True

    def test_gradual_out_accumulation(self):
        """Outs accumulate within half-inning."""
        inning = Inning()

        assert inning.outs == 0
        inning.record_out()
        assert inning.outs == 1
        inning.record_out()
        assert inning.outs == 2
        inning.record_out()
        assert inning.outs == 3

    def test_double_play_scenario(self):
        """Record 2 outs at once (double play)."""
        inning = Inning()
        inning.record_out(2)
        assert inning.outs == 2

    def test_triple_play_scenario(self):
        """Record 3 outs at once (triple play)."""
        inning = Inning()
        inning.record_out(3)
        assert inning.outs == 3


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_direct_attribute_modification(self):
        """Test that attributes can be directly modified."""
        inning = Inning()
        inning.number = 5
        inning.top = False
        inning.outs = 2

        assert inning.number == 5
        assert inning.bottom is True
        assert inning.outs == 2

    def test_negative_inning_number_via_direct_assignment(self):
        """Setting negative inning number raises ValueError."""
        inning = Inning()
        with pytest.raises(
            TypeError,
            match="Inning number must be an integer greater than or equal to 1",
        ):
            inning.number = -1

    def test_excessive_outs_via_direct_assignment(self):
        """Setting more than 3 outs raises ValueError."""
        inning = Inning()
        with pytest.raises(
            ValueError, match="Outs must be an integer between 0 and 3, got 10"
        ):
            inning.outs = 10

    def test_record_out_beyond_three(self):
        """Adding 5 outs raises ValueError."""
        inning = Inning()
        with pytest.raises(ValueError, match="Cannot exceed 3 outs"):
            inning.record_out(5)

    def test_record_negative_outs(self):
        """Recording negative outs raises ValueError."""
        inning = Inning()
        with pytest.raises(ValueError, match="Cannot record negative outs"):
            inning.record_out(-1)

    def test_increment_with_existing_outs(self):
        """Increment resets outs regardless of count."""
        inning = Inning()
        inning.outs = 2  # Valid state
        inning.increment()
        assert inning.outs == 0

    def test_zero_inning_number(self):
        """Setting inning to 0 raises ValueError."""
        inning = Inning()
        with pytest.raises(
            TypeError,
            match="Inning number must be an integer greater than or equal to 1",
        ):
            inning.number = 0

    def test_very_high_inning_number(self):
        """Test with extremely high inning number."""
        inning = Inning()
        inning.number = 50
        assert str(inning) == "Top of 50"

    def test_multiple_increments_from_same_state(self):
        inning = Inning()
        initial_state = (inning.number, inning.top)
        inning.increment()
        inning.increment()
        final_state = (inning.number, inning.top)

        # Should advance 2 half-innings
        assert initial_state == (1, True)
        assert final_state == (2, True)


class TestInningComparison:
    """Test inning progression logic."""

    def test_top_vs_bottom_same_inning(self):
        top = Inning()
        bottom = Inning()
        bottom.top = False

        assert top.number == bottom.number
        assert top.top != bottom.top

    def test_consecutive_half_innings(self):
        first = Inning()
        second = Inning()
        second.increment()

        assert first.number == 1 and first.top is True
        assert second.number == 1 and second.bottom is True

    def test_same_inning_different_outs(self):
        inning1 = Inning()
        inning2 = Inning()

        inning1.record_out(1)
        inning2.record_out(2)

        assert inning1.number == inning2.number
        assert inning1.top == inning2.top
        assert inning1.outs != inning2.outs


class TestPropertyBehavior:
    """Test property behavior specifically."""

    def test_bottom_property_is_readonly(self):
        """bottom is a computed property, can't be set directly."""
        inning = Inning()
        # This should raise AttributeError
        with pytest.raises(AttributeError):
            inning.bottom = True

    def test_bottom_always_inverse_of_top(self):
        """Verify bottom is always !top."""
        inning = Inning()

        for top_value in [True, False, True, False]:
            inning.top = top_value
            assert inning.bottom == (not top_value)

    def test_top_can_be_set(self):
        """top is a regular attribute, can be modified."""
        inning = Inning()
        inning.top = False
        assert inning.top is False
        inning.top = True
        assert inning.top is True


class TestPropertyValidation:
    """Test property setter validation."""

    def test_number_rejects_negative(self):
        inning = Inning()
        with pytest.raises(
            TypeError,
            match="Inning number must be an integer greater than or equal to 1",
        ):
            inning.number = -5

    def test_number_rejects_zero(self):
        inning = Inning()
        with pytest.raises(
            TypeError,
            match="Inning number must be an integer greater than or equal to 1",
        ):
            inning.number = 0

    def test_number_accepts_positive(self):
        inning = Inning()
        inning.number = 15
        assert inning.number == 15

    def test_number_rejects_float(self):
        inning = Inning()
        with pytest.raises(TypeError, match="Inning number must be an integer"):
            inning.number = 3.5

    def test_number_rejects_string(self):
        inning = Inning()
        with pytest.raises(TypeError, match="Inning number must be an integer"):
            inning.number = "5"

    def test_outs_rejects_negative(self):
        inning = Inning()
        with pytest.raises(ValueError, match="Outs must be an integer between 0 and 3"):
            inning.outs = -1

    def test_outs_rejects_above_three(self):
        inning = Inning()
        with pytest.raises(ValueError, match="Outs must be an integer between 0 and 3"):
            inning.outs = 4

    def test_outs_accepts_zero(self):
        inning = Inning()
        inning.outs = 0
        assert inning.outs == 0

    def test_outs_accepts_one_through_three(self):
        inning = Inning()
        for valid_outs in [1, 2, 3]:
            inning.outs = valid_outs
            assert inning.outs == valid_outs

    def test_outs_rejects_float(self):
        inning = Inning()
        with pytest.raises(ValueError, match="Outs must be an integer"):
            inning.outs = 2.5

    def test_outs_rejects_string(self):
        inning = Inning()
        with pytest.raises(ValueError, match="Outs must be an integer"):
            inning.outs = "2"

    def test_is_over_property(self):
        inning = Inning()
        assert inning.is_over is False

        inning.outs = 2
        assert inning.is_over is False

        inning.outs = 3
        assert inning.is_over is True
