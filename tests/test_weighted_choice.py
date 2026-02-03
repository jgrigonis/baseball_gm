# tests/test_weighted_choice.py

import pytest
from random import Random
from typing import Dict

from src.util.weighted_choice import WeightedChoice


class TestWeightedChoiceInitialization:
    """Test initialization and basic setup."""

    def test_init_empty(self):
        """Test initialization with no weights."""
        wc = WeightedChoice()
        assert wc.get_weights() == {}

    def test_init_with_weights(self):
        """Test initialization with initial weights."""
        weights = {"a": 100, "b": 200, "c": 300}
        wc = WeightedChoice(initial_weights=weights)
        assert wc.get_weights() == weights

    def test_init_with_custom_rng(self):
        """Test initialization with custom RNG."""
        rng = Random(42)
        wc = WeightedChoice(rng=rng)
        assert wc.rng is rng

    def test_init_copies_weights(self):
        """Test that initial weights are copied, not referenced."""
        original = {"a": 100, "b": 200}
        wc = WeightedChoice(initial_weights=original)
        original["a"] = 999
        assert wc.get_weights()["a"] == 100


class TestWeightedChoiceSetAndReset:
    """Test setting and resetting weights."""

    def test_set_weights(self):
        """Test setting new weights."""
        wc = WeightedChoice()
        new_weights = {"x": 50, "y": 75}
        wc.set_weights(new_weights)
        assert wc.get_weights() == new_weights

    def test_set_weights_copies(self):
        """Test that set_weights copies the dict."""
        wc = WeightedChoice()
        original = {"a": 100}
        wc.set_weights(original)
        original["a"] = 999
        assert wc.get_weights()["a"] == 100

    def test_reset_to_base_weights(self):
        """Test reset returns to base weights."""
        base = {"a": 100, "b": 200}
        wc = WeightedChoice(initial_weights=base)

        wc.multiply("a", 2.0)
        assert wc.get_weights()["a"] == 200

        wc.reset()
        assert wc.get_weights() == base

    def test_reset_after_set_weights(self):
        """Test reset works after set_weights."""
        wc = WeightedChoice(initial_weights={"a": 100})
        new_base = {"x": 50, "y": 75}
        wc.set_weights(new_base)

        wc.multiply("x", 3.0)
        wc.reset()
        assert wc.get_weights() == new_base


class TestWeightedChoiceModifications:
    """Test weight modification methods."""

    def test_multiply(self):
        """Test multiplying a weight."""
        wc = WeightedChoice({"a": 100, "b": 200})
        wc.multiply("a", 2.0)
        assert wc.get_weights()["a"] == 200
        assert wc.get_weights()["b"] == 200

    def test_multiply_fractional(self):
        """Test multiplying by fraction."""
        wc = WeightedChoice({"a": 100})
        wc.multiply("a", 0.5)
        assert wc.get_weights()["a"] == 50

    def test_multiply_converts_to_int(self):
        """Test multiply converts result to int."""
        wc = WeightedChoice({"a": 100})
        wc.multiply("a", 1.5)
        assert wc.get_weights()["a"] == 150
        assert isinstance(wc.get_weights()["a"], int)

    def test_multiply_nonexistent_key(self):
        """Test multiply on non-existent key does nothing."""
        wc = WeightedChoice({"a": 100})
        wc.multiply("nonexistent", 2.0)
        assert "nonexistent" not in wc.get_weights()

    def test_add_positive(self):
        """Test adding to a weight."""
        wc = WeightedChoice({"a": 100, "b": 200})
        wc.add("a", 50)
        assert wc.get_weights()["a"] == 150
        assert wc.get_weights()["b"] == 200

    def test_add_negative(self):
        """Test subtracting from a weight."""
        wc = WeightedChoice({"a": 100})
        wc.add("a", -30)
        assert wc.get_weights()["a"] == 70

    def test_add_new_outcome(self):
        """Test adding a new outcome."""
        wc = WeightedChoice({"a": 100})
        wc.add("b", 50)
        assert wc.get_weights()["b"] == 50

    def test_set_value(self):
        """Test setting a specific weight."""
        wc = WeightedChoice({"a": 100, "b": 200})
        wc.set("a", 999)
        assert wc.get_weights()["a"] == 999
        assert wc.get_weights()["b"] == 200

    def test_set_new_outcome(self):
        """Test setting a new outcome."""
        wc = WeightedChoice({"a": 100})
        wc.set("b", 50)
        assert wc.get_weights()["b"] == 50

    def test_chained_modifications(self):
        """Test multiple modifications in sequence."""
        wc = WeightedChoice({"a": 100, "b": 200})
        wc.multiply("a", 2.0)
        wc.add("a", 50)
        wc.set("b", 300)
        assert wc.get_weights()["a"] == 250
        assert wc.get_weights()["b"] == 300


class TestWeightedChoiceModifier:
    """Test apply_modifier method."""

    def test_apply_modifier_function(self):
        """Test applying a modifier function."""
        wc = WeightedChoice({"a": 100, "b": 200})

        def modifier(weights: Dict[str, int]) -> None:
            weights["a"] *= 2
            weights["b"] += 50

        wc.apply_modifier(modifier)
        assert wc.get_weights()["a"] == 200
        assert wc.get_weights()["b"] == 250

    def test_apply_modifier_lambda(self):
        """Test applying a lambda modifier."""
        wc = WeightedChoice({"a": 100})
        wc.apply_modifier(lambda w: w.update({"a": 500}))
        assert wc.get_weights()["a"] == 500

    def test_apply_modifier_complex(self):
        """Test complex modifier that adds new outcomes."""
        wc = WeightedChoice({"a": 100, "b": 200})

        def complex_modifier(weights: Dict[str, int]) -> None:
            total = sum(weights.values())
            weights["c"] = total // 2
            weights["a"] = 0

        wc.apply_modifier(complex_modifier)
        assert wc.get_weights()["a"] == 0
        assert wc.get_weights()["c"] == 150


class TestWeightedChoiceChoose:
    """Test the choose method."""

    def test_choose_single_outcome(self):
        """Test choosing with only one outcome."""
        wc = WeightedChoice({"only": 100})
        assert wc.choose() == "only"

    def test_choose_deterministic_with_seed(self):
        """Test that same seed produces same results."""
        rng1 = Random(42)
        wc1 = WeightedChoice({"a": 100, "b": 100}, rng=rng1)
        result1 = wc1.choose()

        rng2 = Random(42)
        wc2 = WeightedChoice({"a": 100, "b": 100}, rng=rng2)
        result2 = wc2.choose()

        assert result1 == result2

    def test_choose_distribution(self):
        """Test that choice distribution roughly matches weights."""
        rng = Random(42)
        wc = WeightedChoice({"a": 7000, "b": 2000, "c": 1000}, rng=rng)

        counts = {"a": 0, "b": 0, "c": 0}
        trials = 10000

        for _ in range(trials):
            result = wc.choose()
            counts[result] += 1

        # Check rough proportions (with generous margins)
        assert 0.65 < counts["a"] / trials < 0.75  # Expected ~0.70
        assert 0.15 < counts["b"] / trials < 0.25  # Expected ~0.20
        assert 0.05 < counts["c"] / trials < 0.15  # Expected ~0.10

    def test_choose_zero_weight_never_selected(self):
        """Test that zero-weight outcomes are never chosen."""
        rng = Random(42)
        wc = WeightedChoice({"a": 100, "b": 0, "c": 100}, rng=rng)

        results = {wc.choose() for _ in range(1000)}
        assert "b" not in results
        assert "a" in results
        assert "c" in results

    def test_choose_negative_weights_clamped(self):
        """Test that negative weights are clamped to zero."""
        rng = Random(42)
        wc = WeightedChoice({"a": 100, "b": -50}, rng=rng)

        results = {wc.choose() for _ in range(100)}
        assert "b" not in results
        assert results == {"a"}

    def test_choose_raises_on_empty(self):
        """Test that choose raises error with no weights."""
        wc = WeightedChoice()
        with pytest.raises(ValueError, match="No weights set"):
            wc.choose()

    def test_choose_raises_on_all_zero(self):
        """Test that choose raises error when all weights are zero."""
        wc = WeightedChoice({"a": 0, "b": 0})
        with pytest.raises(ValueError, match="All weights are zero"):
            wc.choose()

    def test_choose_after_modifications(self):
        """Test choosing after modifying weights."""
        rng = Random(42)
        wc = WeightedChoice({"a": 100, "b": 100}, rng=rng)
        wc.set("a", 0)  # Make 'a' impossible

        results = {wc.choose() for _ in range(100)}
        assert results == {"b"}


class TestWeightedChoiceGetters:
    """Test getter methods."""

    def test_get_weights_returns_copy(self):
        """Test that get_weights returns a copy."""
        wc = WeightedChoice({"a": 100})
        weights = wc.get_weights()
        weights["a"] = 999
        assert wc.get_weights()["a"] == 100

    def test_get_probabilities_simple(self):
        """Test probability calculation."""
        wc = WeightedChoice({"a": 100, "b": 100})
        probs = wc.get_probabilities()
        assert probs["a"] == 0.5
        assert probs["b"] == 0.5

    def test_get_probabilities_unequal(self):
        """Test probability calculation with unequal weights."""
        wc = WeightedChoice({"a": 7000, "b": 2000, "c": 1000})
        probs = wc.get_probabilities()
        assert abs(probs["a"] - 0.7) < 0.001
        assert abs(probs["b"] - 0.2) < 0.001
        assert abs(probs["c"] - 0.1) < 0.001

    def test_get_probabilities_sum_to_one(self):
        """Test that probabilities sum to 1.0."""
        wc = WeightedChoice({"a": 123, "b": 456, "c": 789})
        probs = wc.get_probabilities()
        assert abs(sum(probs.values()) - 1.0) < 0.0001

    def test_get_probabilities_with_zero_weights(self):
        """Test probabilities with some zero weights."""
        wc = WeightedChoice({"a": 100, "b": 0, "c": 100})
        probs = wc.get_probabilities()
        assert probs["a"] == 0.5
        assert probs["b"] == 0.0
        assert probs["c"] == 0.5

    def test_get_probabilities_all_zero(self):
        """Test probabilities when all weights are zero."""
        wc = WeightedChoice({"a": 0, "b": 0})
        probs = wc.get_probabilities()
        assert probs["a"] == 0.0
        assert probs["b"] == 0.0

    def test_get_probabilities_negative_clamped(self):
        """Test probabilities with negative weights."""
        wc = WeightedChoice({"a": 100, "b": -50})
        probs = wc.get_probabilities()
        assert probs["a"] == 1.0
        assert probs["b"] == 0.0


class TestWeightedChoiceEdgeCases:
    """Test edge cases and special scenarios."""

    def test_very_large_weights(self):
        """Test with very large weight values."""
        wc = WeightedChoice({"a": 1000000, "b": 1000000})
        # Should not raise any errors
        result = wc.choose()
        assert result in ["a", "b"]

    def test_very_small_weights(self):
        """Test with very small but positive weights."""
        wc = WeightedChoice({"a": 1, "b": 1})
        result = wc.choose()
        assert result in ["a", "b"]

    def test_many_outcomes(self):
        """Test with many different outcomes."""
        weights = {f"outcome_{i}": 100 for i in range(100)}
        wc = WeightedChoice(weights)
        result = wc.choose()
        assert result.startswith("outcome_")

    def test_highly_skewed_distribution(self):
        """Test with heavily skewed weights."""
        rng = Random(42)
        wc = WeightedChoice({"rare": 1, "common": 9999}, rng=rng)

        results = [wc.choose() for _ in range(1000)]
        common_count = results.count("common")

        # Should be heavily skewed toward "common"
        assert common_count > 990  # At least 99% common

    def test_reset_doesnt_affect_base(self):
        """Test that modifications don't affect base weights."""
        base = {"a": 100, "b": 200}
        wc = WeightedChoice(initial_weights=base)

        wc.multiply("a", 5.0)
        wc.add("b", 300)
        wc.reset()

        # After reset, should be back to original
        assert wc.get_weights() == base

    def test_multiple_resets(self):
        """Test calling reset multiple times."""
        wc = WeightedChoice({"a": 100})
        wc.multiply("a", 2.0)
        wc.reset()
        wc.multiply("a", 3.0)
        wc.reset()
        assert wc.get_weights()["a"] == 100


class TestWeightedChoiceRealWorldScenarios:
    """Test scenarios matching the original use case."""

    def test_pitch_outcome_simulation(self):
        """Test simulating pitch outcomes like in the original code."""
        rng = Random(42)
        wc = WeightedChoice(
            {
                "ball": 10800,
                "foul": 5100,
                "home_run": 280,
                "strike": 7100,
                "in_play": 5855,
            },
            rng=rng,
        )

        # Simulate runners on base adjustments
        wc.multiply("ball", 1.03)
        wc.multiply("strike", 0.97)
        wc.multiply("in_play", 1.18)

        result = wc.choose()
        assert result in ["ball", "foul", "home_run", "strike", "in_play"]

    def test_double_steal_outcomes(self):
        """Test double steal outcome selection."""
        rng = Random(42)
        wc = WeightedChoice(
            {
                "both_safe": 6500,
                "lead_out_trail_safe": 2500,
                "lead_safe_trail_out": 800,
                "both_out": 200,
            },
            rng=rng,
        )

        result = wc.choose()
        assert result in [
            "both_safe",
            "lead_out_trail_safe",
            "lead_safe_trail_out",
            "both_out",
        ]

    def test_bunt_attempt_modifications(self):
        """Test bunt attempt modifications from original code."""
        wc = WeightedChoice(
            {
                "strike": 7100,
                "foul": 5100,
                "home_run": 280,
                "in_play": 5855,
            }
        )

        bunting_skill = 80  # 0-100 scale

        wc.add("strike", -25 * bunting_skill)  # -2000
        wc.add("foul", 25 * (100 - bunting_skill))  # +500
        wc.set("home_run", 0)
        wc.add("in_play", 25 * (100 - bunting_skill))  # +500

        assert wc.get_weights()["strike"] == 5100
        assert wc.get_weights()["home_run"] == 0
        assert wc.get_weights()["foul"] == 5600

    def test_pitch_out_scenario(self):
        """Test pitch-out probability modifications."""
        wc = WeightedChoice(
            {
                "strike": 7100,
                "ball": 10800,
                "foul": 5100,
                "home_run": 280,
            }
        )

        # Pitch-out makes most outcomes very unlikely
        wc.multiply("strike", 0.05)
        wc.multiply("ball", 2.0)
        wc.multiply("foul", 0.05)
        wc.multiply("home_run", 0.01)

        weights = wc.get_weights()
        assert weights["strike"] == 355  # Much reduced
        assert weights["ball"] == 21600  # Doubled
        assert weights["foul"] == 255  # Much reduced
        assert weights["home_run"] == 2  # Almost zero


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
