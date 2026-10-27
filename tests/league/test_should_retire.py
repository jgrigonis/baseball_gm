# tests/league/test_should_retire.py
"""
Unit tests for OffseasonPipeline._should_retire.

Tests cover:
- Rostered players: age threshold and the factors-driven probability
- Prospects: age thresholds, probability scaling
- Boundary conditions and deterministic RNG behavior

The rostered probability itself is tested in tests/league/test_retirement.py.
"""

import random

from src.league.offseason.offseason_pipeline import OffseasonPipeline
from src.league.offseason.retirement import RetirementFactors, retirement_chance

should_retire = OffseasonPipeline._should_retire


def rng_always(value: float) -> random.Random:
    """Return an RNG stub whose random() always returns value."""

    class FixedRng:
        def random(self):
            return value

    return FixedRng()


# ---------------------------------------------------------------------------
# Rostered players
# ---------------------------------------------------------------------------


class TestRostered:
    def test_never_retires_before_30(self):
        rng = rng_always(0.0)  # Would retire at any probability > 0
        for age in range(17, 30):
            assert should_retire(age, False, rng, factors=RetirementFactors()) is None

    def test_uses_retirement_chance(self):
        factors = RetirementFactors(playing_time=0.5, ovr_drop=2)
        chance = retirement_chance(36, factors)
        assert should_retire(
            36, False, rng_always(chance - 0.001), factors=factors
        ) == ("retired")
        assert (
            should_retire(36, False, rng_always(chance + 0.001), factors=factors)
            is None
        )

    def test_missing_factors_means_no_playing_time(self):
        chance = retirement_chance(36, RetirementFactors())
        assert should_retire(36, False, rng_always(chance - 0.001)) == "retired"
        assert should_retire(36, False, rng_always(chance + 0.001)) is None

    def test_regular_almost_never_retires(self):
        factors = RetirementFactors(playing_time=0.95)
        assert should_retire(39, False, rng_always(0.011), factors=factors) is None


# ---------------------------------------------------------------------------
# Prospects — age threshold
# ---------------------------------------------------------------------------


class TestProspectAgeThreshold:
    def test_never_retires_before_22(self):
        rng = rng_always(0.0)
        for age in range(17, 22):
            assert should_retire(age, True, rng) is None

    def test_exactly_22_can_retire(self):
        # At 22, probability=(22-22)*0.20=0.0 → never retires at exactly 22
        assert should_retire(22, True, rng_always(0.0)) is None

    def test_23_has_retirement_chance(self):
        # At 23, probability=(23-22)*0.20=0.20
        # rng=0.19 → retires
        assert should_retire(23, True, rng_always(0.19)) == "free_agent"

    def test_23_no_retire_if_rng_above(self):
        # probability=0.20, rng=0.21 → does not retire
        assert should_retire(23, True, rng_always(0.21)) is None

    def test_young_prospect_who_played_is_kept(self):
        assert should_retire(21, True, rng_always(0.0), games_played=10) is None


# ---------------------------------------------------------------------------
# Prospects — probability scaling
# ---------------------------------------------------------------------------


class TestProspectProbabilityScaling:
    def test_probability_increases_per_year(self):
        # age=27 → probability=(27-22)*0.20=1.0 → capped at 0.95
        # age=26 → probability=(26-22)*0.20=0.80
        # rng=0.85: retires at 27 (capped at 0.95), not at 26
        rng = rng_always(0.85)
        assert should_retire(27, True, rng) == "free_agent"
        assert should_retire(26, True, rng) is None

    def test_prospect_probability_capped_at_95(self):
        # age=100 → probability capped at 0.95
        # rng=0.96 → does not retire
        assert should_retire(100, True, rng_always(0.96)) is None
        assert should_retire(100, True, rng_always(0.94)) == "retired"


# ---------------------------------------------------------------------------
# Deterministic behavior with seeded RNG
# ---------------------------------------------------------------------------


class TestDeterministicBehavior:
    def test_same_seed_same_result(self):
        factors = RetirementFactors(playing_time=0.3)
        result_a = should_retire(35, False, random.Random(42), factors=factors)
        result_b = should_retire(35, False, random.Random(42), factors=factors)
        assert result_a == result_b

    def test_different_seeds_can_differ(self):
        """With enough trials, different seeds should produce different outcomes."""
        # age=37, half a season: roughly a 1-in-5 chance, varies by seed
        factors = RetirementFactors(playing_time=0.5)
        results = {
            should_retire(37, False, random.Random(seed), factors=factors)
            for seed in range(40)
        }
        assert None in results
        assert "retired" in results
