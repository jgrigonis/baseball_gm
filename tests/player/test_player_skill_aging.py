# tests/player/test_player_skill_aging.py
"""
Unit tests for src/player/player_skill_aging.py

Focuses on:
- _cap_dampen() sigmoid behaviour
- All delta functions accept cap=None (backward compatible)
- All delta functions dampen growth when cap is set
- Decline phases ignore cap dampening
- phased_delta() phase resolution and coaching multiplier
- Statistical properties of each delta function over many trials
"""

import random
import unittest

from src.player.player_skill_aging import (
    CAP_BRAKE,
    SkillAging,
    _cap_dampen,
)

# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────


def _fixed_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _mean_delta(fn, age: int, val: float, n: int = 2000, **kwargs) -> float:
    """Run a delta function n times and return the mean."""
    rng = random.Random(0)
    return sum(fn(age, val, rng, **kwargs) for _ in range(n)) / n


# ─────────────────────────────────────────────
#  _cap_dampen
# ─────────────────────────────────────────────


class TestCapDampen(unittest.TestCase):
    def test_no_cap_returns_raw(self):
        """cap=None means no dampening — raw delta passes through unchanged."""
        self.assertEqual(_cap_dampen(5.0, 60.0, None), 5.0)
        self.assertEqual(_cap_dampen(-2.0, 60.0, None), -2.0)

    def test_negative_delta_never_dampened(self):
        """Decline phases should not be dampened regardless of cap."""
        # At cap
        self.assertEqual(_cap_dampen(-3.0, 80.0, 80), -3.0)
        # Well below cap
        self.assertEqual(_cap_dampen(-1.5, 50.0, 80), -1.5)
        # Above cap (can happen via noise)
        self.assertEqual(_cap_dampen(-2.0, 85.0, 80), -2.0)

    def test_zero_delta_passes_through(self):
        self.assertEqual(_cap_dampen(0.0, 70.0, 80), 0.0)

    def test_at_cap_returns_zero(self):
        """At exactly the cap, growth stops."""
        self.assertEqual(_cap_dampen(2.0, 80.0, 80), 0.0)

    def test_above_cap_returns_zero(self):
        """If noise pushed value past cap, growth is still zero."""
        self.assertEqual(_cap_dampen(1.0, 83.0, 80), 0.0)

    def test_at_half_cap_brake_distance(self):
        """At distance=CAP_BRAKE, dampening is exactly 50%."""
        # distance = CAP_BRAKE means val = cap - CAP_BRAKE
        cap = 80
        val = cap - CAP_BRAKE
        result = _cap_dampen(10.0, val, cap)
        self.assertAlmostEqual(result, 5.0, places=5)

    def test_dampening_increases_with_distance(self):
        """Further from cap → less dampening → higher delta."""
        cap = 80
        close = _cap_dampen(5.0, 75.0, cap)  # distance=5
        medium = _cap_dampen(5.0, 60.0, cap)  # distance=20
        far = _cap_dampen(5.0, 40.0, cap)  # distance=40
        self.assertLess(close, medium)
        self.assertLess(medium, far)

    def test_far_from_cap_approaches_raw(self):
        """Very far from cap, dampening is reduced but not negligible."""
        cap = 100
        result = _cap_dampen(5.0, 1.0, cap)  # distance=99
        # formula: 5.0 * 99 / (99 + 15) ≈ 4.34
        self.assertGreater(result, 4.0)
        self.assertLessEqual(result, 5.0)

    def test_sigmoid_formula(self):
        """Verify formula: delta * distance / (distance + CAP_BRAKE)."""
        raw = 3.0
        val = 60.0
        cap = 80
        distance = cap - val  # 20
        expected = raw * distance / (distance + CAP_BRAKE)
        self.assertAlmostEqual(_cap_dampen(raw, val, cap), expected, places=10)


# ─────────────────────────────────────────────
#  phased_delta
# ─────────────────────────────────────────────


class TestPhasedDelta(unittest.TestCase):
    def setUp(self):
        self.sa = SkillAging()

    def test_phase_resolution_early(self):
        """Young player should be in first phase (positive rate)."""
        mean = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [24, 29, 33], [1.6, 0.2, -1.0, -1.8], [0.5, 0.4, 0.5, 0.6]
            ),
            age=20,
            val=50.0,
        )
        self.assertGreater(mean, 1.0)

    def test_phase_resolution_late(self):
        """Old player should be in last phase (negative rate)."""
        mean = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [24, 29, 33], [1.6, 0.2, -1.0, -1.8], [0.5, 0.4, 0.5, 0.6]
            ),
            age=36,
            val=50.0,
        )
        self.assertLess(mean, 0.0)

    def test_coaching_multiplier_scales_coached_phase(self):
        """Coaching multiplier should scale delta in coached phases."""
        coached = [True]
        mean_1x = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [30], [1.0, -0.5], [0.3, 0.3], coached=coached, coaching=1.0
            ),
            age=25,
            val=50.0,
        )
        mean_2x = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [30], [1.0, -0.5], [0.3, 0.3], coached=coached, coaching=2.0
            ),
            age=25,
            val=50.0,
        )
        self.assertAlmostEqual(mean_2x, mean_1x * 2, delta=0.15)

    def test_coaching_no_effect_on_uncoached_phase(self):
        """Coaching multiplier should not affect uncoached phases."""
        coached = [False]
        mean_1x = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [30], [1.0, -0.5], [0.3, 0.3], coached=coached, coaching=1.0
            ),
            age=25,
            val=50.0,
        )
        mean_2x = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, [30], [1.0, -0.5], [0.3, 0.3], coached=coached, coaching=2.0
            ),
            age=25,
            val=50.0,
        )
        self.assertAlmostEqual(mean_1x, mean_2x, delta=0.15)

    def test_cap_dampens_growth(self):
        """Cap should reduce growth vs no cap."""
        breaks = [30]
        rates = [2.0, -1.0]
        noises = [0.5, 0.5]
        mean_no_cap = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, breaks, rates, noises, cap=None
            ),
            age=25,
            val=70.0,
        )
        mean_with_cap = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, breaks, rates, noises, cap=80
            ),
            age=25,
            val=70.0,
        )
        self.assertGreater(mean_no_cap, mean_with_cap)

    def test_cap_does_not_dampen_decline(self):
        """Cap should not affect decline phase deltas."""
        breaks = [30]
        rates = [2.0, -1.5]
        noises = [0.5, 0.5]
        mean_no_cap = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, breaks, rates, noises, cap=None
            ),
            age=35,
            val=70.0,
        )
        mean_with_cap = _mean_delta(
            lambda a, v, r, **kw: self.sa.phased_delta(
                a, v, r, breaks, rates, noises, cap=80
            ),
            age=35,
            val=70.0,
        )
        self.assertAlmostEqual(mean_no_cap, mean_with_cap, delta=0.1)


# ─────────────────────────────────────────────
#  Individual delta functions — cap=None backward compat
# ─────────────────────────────────────────────


class TestDeltaFunctionsNoCap(unittest.TestCase):
    """All delta functions should work without a cap (legacy behaviour)."""

    def setUp(self):
        self.rng = _fixed_rng()
        self.sa = SkillAging()

    def _runs_without_error(self, fn, age, val, **kwargs):
        for _ in range(10):
            fn(age, val, self.rng, **kwargs)

    def test_delta_SP_no_cap(self):
        self._runs_without_error(self.sa.delta_SP, 22, 60.0)

    def test_delta_PO_no_cap(self):
        self._runs_without_error(self.sa.delta_PO, 25, 55.0)

    def test_delta_AR_no_cap(self):
        self._runs_without_error(self.sa.delta_AR, 24, 65.0)

    def test_delta_KK_no_cap(self):
        self._runs_without_error(self.sa.delta_KK, 22, 50.0)

    def test_delta_CL_no_cap(self):
        for _ in range(10):
            self.sa.delta_CL(30, 55.0, self.rng)

    def test_delta_EY_no_cap(self):
        self._runs_without_error(self.sa.delta_EY, 25, 52.0)

    def test_delta_CT_no_cap(self):
        self._runs_without_error(self.sa.delta_CT, 25, 50.0)

    def test_delta_BR_no_cap(self):
        self._runs_without_error(self.sa.delta_BR, 28, 55.0)

    def test_delta_AC_no_cap(self):
        for _ in range(10):
            self.sa.delta_AC(28, 55.0, self.rng)

    def test_delta_ST_no_cap(self):
        self._runs_without_error(self.sa.delta_ST, 25, 50.0)

    def test_delta_RE_no_cap(self):
        self._runs_without_error(self.sa.delta_RE, 25, 48.0)

    def test_delta_BU_no_cap(self):
        for _ in range(10):
            self.sa.delta_BU(25, 40.0, self.rng)

    def test_delta_CA_no_cap(self):
        for _ in range(10):
            self.sa.delta_CA(28, 55.0, self.rng)

    def test_delta_IF_no_cap(self):
        for _ in range(10):
            self.sa.delta_IF(25, 50.0, self.rng)

    def test_delta_OF_no_cap(self):
        for _ in range(10):
            self.sa.delta_OF(25, 48.0, self.rng)

    def test_delta_GB_no_cap(self):
        for _ in range(10):
            self.sa.delta_GB(24, 45.0, self.rng)


# ─────────────────────────────────────────────
#  Cap dampening per delta function
# ─────────────────────────────────────────────


class TestDeltaFunctionsWithCap(unittest.TestCase):
    """
    For each growth-phase delta, verify:
    - cap set far away → roughly same as no cap
    - cap set close → meaningfully reduced delta
    - cap set at current value → near-zero delta
    - decline phase → cap has no effect
    """

    def setUp(self):
        self.sa = SkillAging()

    def _assert_cap_reduces_growth(self, fn, age, val, cap_close, **kwargs):
        mean_no_cap = _mean_delta(fn, age, val, **kwargs)
        mean_capped = _mean_delta(fn, age, val, cap=cap_close, **kwargs)
        self.assertGreater(
            mean_no_cap,
            mean_capped,
            f"Cap should reduce growth at age={age}, val={val}, cap={cap_close}",
        )

    def _assert_cap_stops_growth(self, fn, age, val, **kwargs):
        """At the cap, mean growth should be near zero."""
        mean = _mean_delta(fn, age, val, cap=int(val), **kwargs)
        self.assertAlmostEqual(mean, 0.0, delta=0.4)

    def _assert_decline_ignores_cap(self, fn, age, val, cap, **kwargs):
        mean_no_cap = _mean_delta(fn, age, val, **kwargs)
        mean_capped = _mean_delta(fn, age, val, cap=cap, **kwargs)
        self.assertAlmostEqual(mean_no_cap, mean_capped, delta=0.2)

    # ── SP ──
    def test_SP_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_SP, age=20, val=60.0, cap_close=65
        )

    def test_SP_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_SP, age=20, val=70.0)

    def test_SP_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_SP, age=35, val=40.0, cap=45)

    # ── PO ──
    def test_PO_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_PO, age=22, val=55.0, cap_close=62
        )

    def test_PO_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_PO, age=22, val=65.0)

    def test_PO_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_PO, age=36, val=50.0, cap=55)

    # ── AR ──
    def test_AR_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_AR, age=20, val=60.0, cap_close=65
        )

    def test_AR_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_AR, age=20, val=70.0)

    def test_AR_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_AR, age=35, val=55.0, cap=58)

    # ── KK ──
    def test_KK_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_KK, age=20, val=55.0, cap_close=62
        )

    def test_KK_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_KK, age=20, val=65.0)

    def test_KK_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_KK, age=35, val=45.0, cap=50)

    # ── EY ──
    def test_EY_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_EY, age=22, val=60.0, cap_close=68
        )

    def test_EY_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_EY, age=22, val=70.0)

    def test_EY_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_EY, age=37, val=55.0, cap=58)

    # ── CT ──
    def test_CT_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_CT, age=22, val=55.0, cap_close=63
        )

    def test_CT_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_CT, age=22, val=65.0)

    def test_CT_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_CT, age=38, val=55.0, cap=58)

    # ── BR ──
    def test_BR_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_BR, age=25, val=60.0, cap_close=68
        )

    def test_BR_cap_stops_growth(self):
        self._assert_cap_stops_growth(self.sa.delta_BR, age=25, val=72.0)

    # ── AC ──
    def test_AC_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_AC, age=25, val=55.0)
        mean_capped = _mean_delta(self.sa.delta_AC, age=25, val=55.0, cap=62)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_AC_cap_stops_growth(self):
        mean = _mean_delta(self.sa.delta_AC, age=25, val=70.0, cap=70)
        self.assertAlmostEqual(mean, 0.0, delta=0.3)

    def test_AC_positive_on_average(self):
        """AC growth phase should trend positive, not strictly always positive."""
        rng = random.Random(0)
        deltas = [self.sa.delta_AC(30, 60.0, rng) for _ in range(500)]
        self.assertGreater(sum(deltas) / len(deltas), 0.0)

    # ── ST ──
    def test_ST_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_ST, age=22, val=50.0, cap_close=58
        )

    def test_ST_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_ST, age=34, val=55.0, cap=58)

    # ── RE ──
    def test_RE_cap_reduces_growth(self):
        self._assert_cap_reduces_growth(
            self.sa.delta_RE, age=22, val=50.0, cap_close=60
        )

    def test_RE_decline_ignores_cap(self):
        self._assert_decline_ignores_cap(self.sa.delta_RE, age=35, val=50.0, cap=55)

    # ── BU ──
    def test_BU_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_BU, age=25, val=45.0)
        mean_capped = _mean_delta(self.sa.delta_BU, age=25, val=45.0, cap=52)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_BU_positive_on_average(self):
        rng = random.Random(0)
        deltas = [self.sa.delta_BU(25, 40.0, rng) for _ in range(500)]
        self.assertGreater(sum(deltas) / len(deltas), 0.0)

    # ── CA ──
    def test_CA_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_CA, age=25, val=50.0)
        mean_capped = _mean_delta(self.sa.delta_CA, age=25, val=50.0, cap=58)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_CA_decline_ignores_cap(self):
        """After decline age, cap should have no effect."""
        mean_no_cap = _mean_delta(self.sa.delta_CA, age=35, val=65.0)
        mean_capped = _mean_delta(self.sa.delta_CA, age=35, val=65.0, cap=70)
        self.assertAlmostEqual(mean_no_cap, mean_capped, delta=0.2)

    # ── IF ──
    def test_IF_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_IF, age=22, val=50.0)
        mean_capped = _mean_delta(self.sa.delta_IF, age=22, val=50.0, cap=60)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_IF_decline_ignores_cap(self):
        mean_no_cap = _mean_delta(self.sa.delta_IF, age=35, val=55.0)
        mean_capped = _mean_delta(self.sa.delta_IF, age=35, val=55.0, cap=58)
        self.assertAlmostEqual(mean_no_cap, mean_capped, delta=0.2)

    # ── OF ──
    def test_OF_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_OF, age=22, val=50.0)
        mean_capped = _mean_delta(self.sa.delta_OF, age=22, val=50.0, cap=58)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_OF_decline_ignores_cap(self):
        mean_no_cap = _mean_delta(self.sa.delta_OF, age=34, val=50.0)
        mean_capped = _mean_delta(self.sa.delta_OF, age=34, val=50.0, cap=55)
        self.assertAlmostEqual(mean_no_cap, mean_capped, delta=0.2)

    # ── GB ──
    def test_GB_cap_reduces_growth(self):
        mean_no_cap = _mean_delta(self.sa.delta_GB, age=22, val=45.0)
        mean_capped = _mean_delta(self.sa.delta_GB, age=22, val=45.0, cap=55)
        self.assertGreater(mean_no_cap, mean_capped)

    def test_GB_decline_ignores_cap(self):
        mean_no_cap = _mean_delta(self.sa.delta_GB, age=35, val=50.0)
        mean_capped = _mean_delta(self.sa.delta_GB, age=35, val=50.0, cap=55)
        self.assertAlmostEqual(mean_no_cap, mean_capped, delta=0.2)


# ─────────────────────────────────────────────
#  CL special case
# ─────────────────────────────────────────────


class TestDeltaCL(unittest.TestCase):
    def test_vet_bonus_applied_at_and_after_vet_age(self):
        """Players 28+ should trend slightly positive on average."""
        mean_vet = _mean_delta(
            lambda a, v, r, **kw: SkillAging.delta_CL(a, v, r), age=30, val=50.0, n=5000
        )
        self.assertGreater(mean_vet, 0.0)

    def test_no_vet_bonus_before_vet_age(self):
        """Young players have only a small baseline drift."""
        mean_young = _mean_delta(
            lambda a, v, r, **kw: SkillAging.delta_CL(a, v, r), age=24, val=50.0, n=5000
        )
        self.assertAlmostEqual(mean_young, 0.5, delta=0.15)

    def test_playoff_boost_adds_to_delta(self):
        mean_no_boost = _mean_delta(
            lambda a, v, r, **kw: SkillAging.delta_CL(a, v, r, playoff_boost=0.0),
            age=25,
            val=50.0,
            n=2000,
        )
        mean_boosted = _mean_delta(
            lambda a, v, r, **kw: SkillAging.delta_CL(a, v, r, playoff_boost=1.0),
            age=25,
            val=50.0,
            n=2000,
        )
        self.assertAlmostEqual(mean_boosted - mean_no_boost, 1.0, delta=0.15)


# ─────────────────────────────────────────────
#  Cross-player cap variance
# ─────────────────────────────────────────────


class TestCapVarianceAcrossPlayers(unittest.TestCase):
    """
    Two players at the same base with different caps should develop
    to measurably different values over a simulated career.
    """

    def _simulate(self, start: float, cap: int | None, ages) -> float:
        sa = SkillAging()
        rng = random.Random(42)
        val = start
        for age in ages:
            val += sa.delta_CT(age, val, rng, cap=cap)
            val = max(1.0, min(100.0, val))
        return val

    def test_high_cap_player_develops_further(self):
        ages = list(range(17, 33))
        low_cap_final = self._simulate(50.0, cap=58, ages=ages)
        high_cap_final = self._simulate(50.0, cap=82, ages=ages)
        self.assertGreater(high_cap_final, low_cap_final)

    def test_capped_player_does_not_exceed_cap_on_average(self):
        """Mean final value across many trials should stay at or below cap."""
        sa = SkillAging()
        cap = 62
        finals = []
        for seed in range(300):
            rng = random.Random(seed)
            val = 50.0
            for age in range(17, 33):
                val += sa.delta_CT(age, val, rng, cap=cap)
                val = max(1.0, min(100.0, val))
            finals.append(val)
        mean_final = sum(finals) / len(finals)
        # Mean should be at or below cap (noise may occasionally push past)
        self.assertLessEqual(mean_final, cap + 2.0)

    def test_uncapped_player_grows_higher_than_capped(self):
        """Over a career, uncapped growth outpaces capped growth."""
        sa = SkillAging()
        ages = list(range(17, 32))

        def run(cap, seed):
            rng = random.Random(seed)
            val = 50.0
            for age in ages:
                val += sa.delta_EY(age, val, rng, cap=cap)
                val = max(1.0, min(100.0, val))
            return val

        n = 200
        mean_capped = sum(run(cap=65, seed=i) for i in range(n)) / n
        mean_uncapped = sum(run(cap=None, seed=i) for i in range(n)) / n
        self.assertGreater(mean_uncapped, mean_capped)


if __name__ == "__main__":
    unittest.main()
