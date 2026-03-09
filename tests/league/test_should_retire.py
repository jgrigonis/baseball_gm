# tests/league/test_should_retire.py
"""
Unit tests for OffseasonPipeline._should_retire.

Tests cover:
- Rostered players: age thresholds, probability scaling, skill decline factor
- Prospects: age thresholds, probability scaling
- Boundary conditions and deterministic RNG behavior
"""

import random

from src.league.offseason.offseason_pipeline import OffseasonPipeline

should_retire = OffseasonPipeline._should_retire


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockSkills:
    """Minimal skills stand-in with controllable average."""

    def __init__(self, avg: int = 50):
        self._avg = avg

    def as_dict(self) -> dict:
        # Return 16 skills all equal to avg so the average is exact
        return {f"skill_{i}": self._avg for i in range(16)}


def rng_always(value: float) -> random.Random:
    """Return a seeded RNG whose first random() call returns a predictable value."""

    # Patch random() directly via a simple stub
    class FixedRng:
        def random(self):
            return value

    return FixedRng()


# ---------------------------------------------------------------------------
# Rostered players — age threshold
# ---------------------------------------------------------------------------


class TestRosteredAgeThreshold:
    def test_never_retires_before_30(self):
        rng = rng_always(0.0)  # Would retire at any probability > 0
        for age in range(17, 30):
            assert should_retire(age, MockSkills(50), False, rng) is False

    def test_exactly_30_can_retire(self):
        # At 30, base = (30-30)*0.04 = 0.0 — no retirement chance at exactly 30
        assert should_retire(30, MockSkills(50), False, rng_always(0.0)) is False

    def test_age_31_first_retirement_chance(self):
        # At 31, base = (31-30)*0.04 = 0.04
        # rng=0.03 → retires
        assert should_retire(31, MockSkills(50), False, rng_always(0.03)) is True

    def test_age_31_no_retire_if_rng_above(self):
        # probability=0.04, rng=0.05 → does not retire
        assert should_retire(31, MockSkills(50), False, rng_always(0.05)) is False


# ---------------------------------------------------------------------------
# Rostered players — probability scaling with age
# ---------------------------------------------------------------------------


class TestRosteredProbabilityScaling:
    def test_probability_increases_with_age(self):
        # At age 40, base = (40-30)*0.04 = 0.40
        # rng=0.39 → retires; at age 30 base=0.04 → rng=0.39 → does not retire
        skills = MockSkills(50)
        assert should_retire(40, skills, False, rng_always(0.39)) is True
        assert should_retire(30, skills, False, rng_always(0.39)) is False

    def test_probability_capped_at_95_percent(self):
        # Extremely old player with terrible skills — still only 95% chance
        # rng=0.96 → should not retire even at 99 years old
        assert should_retire(99, MockSkills(1), False, rng_always(0.96)) is False

    def test_probability_at_cap_retires(self):
        assert should_retire(99, MockSkills(1), False, rng_always(0.94)) is True


# ---------------------------------------------------------------------------
# Rostered players — skill decline factor
# ---------------------------------------------------------------------------


class TestRosteredSkillDecline:
    def test_low_skill_avg_increases_retirement_chance(self):
        # age=32, base=(32-30)*0.04=0.08
        # skill_avg=30 → decline_factor=(50-30)/100=0.20 → probability=0.28
        # skill_avg=50 → decline_factor=0 → probability=0.08
        # rng=0.15: retires if skill_avg=30, not if skill_avg=50
        rng = rng_always(0.15)
        assert should_retire(32, MockSkills(30), False, rng) is True
        assert should_retire(32, MockSkills(50), False, rng) is False

    def test_above_average_skills_no_decline_bonus(self):
        # skill_avg=80 → decline_factor=0, same probability as skill_avg=50
        # age=32, base=0.08 — both should produce same result
        rng = rng_always(0.05)
        assert should_retire(32, MockSkills(80), False, rng) is True  # 0.05 < 0.08
        assert should_retire(32, MockSkills(50), False, rng) is True  # same probability

    def test_skill_avg_50_no_decline_factor(self):
        # age=31, base=0.04, decline_factor=0
        # rng=0.03 → retires
        assert should_retire(31, MockSkills(50), False, rng_always(0.03)) is True


# ---------------------------------------------------------------------------
# Prospects — age threshold
# ---------------------------------------------------------------------------


class TestProspectAgeThreshold:
    def test_never_retires_before_22(self):
        rng = rng_always(0.0)
        for age in range(17, 22):
            assert should_retire(age, MockSkills(50), True, rng) is False

    def test_exactly_22_can_retire(self):
        # At 22, probability=(22-22)*0.20=0.0 → never retires at exactly 22
        assert should_retire(22, MockSkills(50), True, rng_always(0.0)) is False

    def test_23_has_retirement_chance(self):
        # At 23, probability=(23-22)*0.20=0.20
        # rng=0.19 → retires
        assert should_retire(23, MockSkills(50), True, rng_always(0.19)) is True

    def test_23_no_retire_if_rng_above(self):
        # probability=0.20, rng=0.21 → does not retire
        assert should_retire(23, MockSkills(50), True, rng_always(0.21)) is False


# ---------------------------------------------------------------------------
# Prospects — probability scaling
# ---------------------------------------------------------------------------


class TestProspectProbabilityScaling:
    def test_probability_increases_per_year(self):
        # age=27 → probability=(27-22)*0.20=1.0 → capped at 0.95
        # age=26 → probability=(26-22)*0.20=0.80
        # rng=0.85: retires at 27 (capped at 0.95), not at 26
        rng = rng_always(0.85)
        assert should_retire(27, MockSkills(50), True, rng) is True
        assert should_retire(26, MockSkills(50), True, rng) is False

    def test_prospect_probability_capped_at_95(self):
        # age=100 → probability capped at 0.95
        # rng=0.96 → does not retire
        assert should_retire(100, MockSkills(50), True, rng_always(0.96)) is False
        assert should_retire(100, MockSkills(50), True, rng_always(0.94)) is True

    def test_prospect_skills_do_not_affect_probability(self):
        # Prospects retire based on age only, not skill level
        rng = rng_always(0.19)
        assert should_retire(23, MockSkills(10), True, rng) is True
        assert should_retire(23, MockSkills(90), True, rng) is True


# ---------------------------------------------------------------------------
# Deterministic behavior with seeded RNG
# ---------------------------------------------------------------------------


class TestDeterministicBehavior:
    def test_same_seed_same_result(self):
        skills = MockSkills(45)
        result_a = should_retire(35, skills, False, random.Random(42))
        result_b = should_retire(35, skills, False, random.Random(42))
        assert result_a == result_b

    def test_different_seeds_can_differ(self):
        """With enough trials, different seeds should produce different outcomes."""
        skills = MockSkills(50)
        # age=38: base=(38-30)*0.04=0.32 — roughly 1/3 chance, varies by seed
        results = {
            should_retire(38, skills, False, random.Random(seed)) for seed in range(20)
        }
        # Should see both True and False across 20 seeds
        assert True in results
        assert False in results
