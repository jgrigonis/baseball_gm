# tests/player/test_talent_caps.py
"""
Unit tests for src/player/talent_caps.py

Tests cover:
- expected_growth() bucketing and boundary conditions
- generate_talent_caps() properties: cap >= base, cap <= 100,
  all skills present, reproducibility, variance across players
"""

import random
import unittest

from src.player.player_skill_aging import planned_growth
from src.player.talent_caps import (
    ELITE_MIN_ROOM,
    FLOOR_ROOM,
    TALENT_SIGMA,
    _DEFAULT_SIGMA,
    expected_growth,
    generate_talent_caps,
)

# All 16 skill names as used in the system
_ALL_SKILLS = [
    "clutch",
    "speed",
    "power",
    "eye",
    "contact",
    "base_running",
    "bunting",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "stamina",
    "recovery",
    "ground_balls",
    "strikes",
]

# A realistic full skills dict (all keys present, values in 1-100)
_SAMPLE_SKILLS: dict[str, int] = {
    "clutch": 52,
    "speed": 61,
    "power": 45,
    "eye": 48,
    "contact": 53,
    "base_running": 50,
    "bunting": 38,
    "catching": 30,
    "infield": 42,
    "outfield": 44,
    "arm": 67,
    "accuracy": 35,
    "stamina": 40,
    "recovery": 38,
    "ground_balls": 33,
    "strikes": 41,
}


# ─────────────────────────────────────────────
#  expected_growth
# ─────────────────────────────────────────────


class TestExpectedGrowth(unittest.TestCase):
    def test_normal_range_gets_full_planned_growth(self):
        """Across the normal range a cap leaves room for the whole curve."""
        for base in [25, 40, 55, 69]:
            with self.subTest(base=base):
                self.assertEqual(
                    expected_growth(base, "contact"), planned_growth("contact")
                )

    def test_floor_skill_gets_a_fraction(self):
        """Floor-level skills (no latent talent) barely grow."""
        for base in [1, 10, 24]:
            with self.subTest(base=base):
                self.assertAlmostEqual(
                    expected_growth(base, "contact"),
                    planned_growth("contact") * FLOOR_ROOM,
                )

    def test_elite_skill_tapers_but_keeps_half(self):
        """Elite skills have less room, but never less than half the curve."""
        full = planned_growth("contact")
        self.assertLess(expected_growth(80, "contact"), full)
        self.assertGreater(expected_growth(80, "contact"), full * ELITE_MIN_ROOM)
        for base in [90, 100]:
            with self.subTest(base=base):
                self.assertAlmostEqual(
                    expected_growth(base, "contact"), full * ELITE_MIN_ROOM
                )

    def test_growth_decreases_at_high_end(self):
        """Elite players have less room to grow than average players."""
        self.assertGreater(expected_growth(50, "eye"), expected_growth(80, "eye"))

    def test_follows_the_aging_curve(self):
        """Skills the curve grows more get more room (eye vs speed)."""
        self.assertGreater(expected_growth(50, "eye"), expected_growth(50, "speed"))

    def test_unknown_skill_uses_default(self):
        self.assertGreater(expected_growth(50, "mystery_skill"), 0)

    def test_returns_float(self):
        self.assertIsInstance(expected_growth(50, "eye"), float)


# ─────────────────────────────────────────────
#  TALENT_SIGMA constants
# ─────────────────────────────────────────────


class TestTalentSigma(unittest.TestCase):
    def test_all_skills_have_sigma(self):
        """Every skill should have an explicit sigma entry."""
        for sk in _ALL_SKILLS:
            with self.subTest(skill=sk):
                self.assertIn(sk, TALENT_SIGMA, f"{sk} missing from TALENT_SIGMA")

    def test_sigma_values_positive(self):
        for sk, sigma in TALENT_SIGMA.items():
            with self.subTest(skill=sk):
                self.assertGreater(sigma, 0, f"{sk} sigma must be > 0")

    def test_clutch_is_most_unpredictable(self):
        """Clutch should have the highest sigma — essentially unknowable."""
        self.assertEqual(max(TALENT_SIGMA.values()), TALENT_SIGMA["clutch"])

    def test_arm_is_more_predictable_than_contact(self):
        """Arm strength (radar gun) more predictable than contact (needs sample)."""
        self.assertLess(TALENT_SIGMA["arm"], TALENT_SIGMA["contact"])

    def test_bunting_is_more_predictable_than_recovery(self):
        """Bunting is pure technique; recovery nearly invisible."""
        self.assertLess(TALENT_SIGMA["bunting"], TALENT_SIGMA["recovery"])

    def test_default_sigma_positive(self):
        self.assertGreater(_DEFAULT_SIGMA, 0)


# ─────────────────────────────────────────────
#  generate_talent_caps
# ─────────────────────────────────────────────


class TestGenerateTalentCapsStructure(unittest.TestCase):
    """Tests for the shape and types of the output."""

    def setUp(self):
        self.rng = random.Random(42)
        self.caps = generate_talent_caps(_SAMPLE_SKILLS, self.rng)

    def test_returns_dict(self):
        self.assertIsInstance(self.caps, dict)

    def test_all_skills_present(self):
        for sk in _ALL_SKILLS:
            with self.subTest(skill=sk):
                self.assertIn(sk, self.caps)

    def test_all_values_are_integers(self):
        for sk, val in self.caps.items():
            with self.subTest(skill=sk):
                self.assertIsInstance(val, int, f"{sk} cap should be int")

    def test_all_values_in_range(self):
        for sk, val in self.caps.items():
            with self.subTest(skill=sk):
                self.assertGreaterEqual(val, 1, f"{sk} cap below minimum")
                self.assertLessEqual(val, 100, f"{sk} cap above maximum")


class TestGenerateTalentCapsInvariants(unittest.TestCase):
    """Tests for the key design invariants."""

    def test_cap_never_below_base(self):
        """Cap must always be >= base skill value."""
        rng = random.Random(0)
        for trial in range(200):
            caps = generate_talent_caps(_SAMPLE_SKILLS, rng)
            for sk, base in _SAMPLE_SKILLS.items():
                with self.subTest(trial=trial, skill=sk):
                    self.assertGreaterEqual(
                        caps[sk], base, f"{sk}: cap {caps[sk]} < base {base}"
                    )

    def test_cap_never_exceeds_100(self):
        """Cap is hard-capped at 100 regardless of growth roll."""
        rng = random.Random(1)
        # Use high base values to stress-test the 100 ceiling
        high_skills = {sk: 95 for sk in _ALL_SKILLS}
        for _ in range(100):
            caps = generate_talent_caps(high_skills, rng)
            for sk, val in caps.items():
                self.assertLessEqual(val, 100, f"{sk} exceeded 100")

    def test_floor_skill_cap_is_near_base(self):
        """Skills at base < 25 should have caps close to their base (small growth)."""
        rng = random.Random(42)
        floor_skills = {sk: 10 for sk in _ALL_SKILLS}
        results = [generate_talent_caps(floor_skills, rng) for _ in range(300)]
        for sk in _ALL_SKILLS:
            avg_cap = sum(r[sk] for r in results) / len(results)
            # Floor skills get FLOOR_ROOM of the planned growth (at most ~8)
            self.assertLess(
                avg_cap, 30, f"{sk}: floor skill cap too high ({avg_cap:.1f})"
            )

    def test_average_skill_has_more_growth_than_elite(self):
        """Average base (50) produces higher caps on average than elite base (85)."""
        rng = random.Random(42)
        avg_skills = {sk: 50 for sk in _ALL_SKILLS}
        elite_skills = {sk: 85 for sk in _ALL_SKILLS}

        n = 500
        avg_caps = [generate_talent_caps(avg_skills, rng) for _ in range(n)]
        elite_caps = [generate_talent_caps(elite_skills, rng) for _ in range(n)]

        # Compare growth (cap - base), not absolute cap
        avg_growth = sum(r["contact"] - 50 for r in avg_caps) / n
        elite_growth = sum(r["contact"] - 85 for r in elite_caps) / n

        self.assertGreater(avg_growth, elite_growth)


class TestGenerateTalentCapsReproducibility(unittest.TestCase):
    def test_same_seed_same_caps(self):
        """Identical seed and skills produce identical caps."""
        caps1 = generate_talent_caps(_SAMPLE_SKILLS, random.Random(99))
        caps2 = generate_talent_caps(_SAMPLE_SKILLS, random.Random(99))
        self.assertEqual(caps1, caps2)

    def test_different_seeds_different_caps(self):
        """Different seeds almost certainly produce different caps."""
        caps1 = generate_talent_caps(_SAMPLE_SKILLS, random.Random(1))
        caps2 = generate_talent_caps(_SAMPLE_SKILLS, random.Random(2))
        self.assertNotEqual(caps1, caps2)

    def test_rng_state_advances(self):
        """Calling generate_talent_caps advances the RNG (doesn't reset it)."""
        rng = random.Random(42)
        caps1 = generate_talent_caps(_SAMPLE_SKILLS, rng)
        caps2 = generate_talent_caps(_SAMPLE_SKILLS, rng)
        # After consuming RNG state, second call should differ from first
        self.assertNotEqual(caps1, caps2)


class TestGenerateTalentCapsVariance(unittest.TestCase):
    """Tests that caps have meaningful variance — two players aren't identical."""

    def test_two_identical_players_get_different_caps(self):
        """Same base skills, sequential RNG draws → different caps."""
        rng = random.Random(7)
        caps1 = generate_talent_caps(_SAMPLE_SKILLS, rng)
        caps2 = generate_talent_caps(_SAMPLE_SKILLS, rng)
        # Extremely unlikely all 16 skills are identical
        self.assertNotEqual(caps1, caps2)

    def test_high_sigma_skill_has_more_variance_than_low_sigma(self):
        """Contact (sigma=12) should vary more than arm (sigma=6) across players."""
        rng = random.Random(42)
        base = 50
        skills = {sk: base for sk in _ALL_SKILLS}
        n = 500
        results = [generate_talent_caps(skills, rng) for _ in range(n)]

        contact_caps = [r["contact"] for r in results]
        arm_caps = [r["arm"] for r in results]

        contact_variance = (
            sum((v - sum(contact_caps) / n) ** 2 for v in contact_caps) / n
        )
        arm_variance = sum((v - sum(arm_caps) / n) ** 2 for v in arm_caps) / n

        self.assertGreater(contact_variance, arm_variance)

    def test_caps_not_all_identical_across_population(self):
        """Generating 50 players should produce meaningful spread in caps."""
        rng = random.Random(42)
        results = [generate_talent_caps(_SAMPLE_SKILLS, rng) for _ in range(50)]
        # Each skill should have at least 2 distinct values across 50 players
        for sk in _ALL_SKILLS:
            values = {r[sk] for r in results}
            self.assertGreater(
                len(values), 1, f"{sk} has no variance across 50 players"
            )


class TestGenerateTalentCapsMissingSkills(unittest.TestCase):
    def test_empty_skills_dict_returns_empty(self):
        caps = generate_talent_caps({}, random.Random(1))
        self.assertEqual(caps, {})

    def test_single_skill(self):
        caps = generate_talent_caps({"speed": 55}, random.Random(1))
        self.assertIn("speed", caps)
        self.assertGreaterEqual(caps["speed"], 55)
        self.assertLessEqual(caps["speed"], 100)

    def test_unknown_skill_uses_default_sigma(self):
        """A skill not in TALENT_SIGMA should still generate without error."""
        caps = generate_talent_caps({"mystery_skill": 50}, random.Random(1))
        self.assertIn("mystery_skill", caps)
        self.assertGreaterEqual(caps["mystery_skill"], 50)


if __name__ == "__main__":
    unittest.main()
