# src/player/player_skill_aging.py
"""
Player Skill Aging

Each delta function returns the expected one-year change in a skill.
Constants are grouped by skill above each function for easy tuning.

Phase breaks are always ascending. phased_delta() resolves the phase
using age < break, so the last rate/noise applies for all remaining ages.

Ceiling dampening (per-player soft caps):
  Growth slows as a player approaches their talent cap using a sigmoid:
      dampening = distance / (distance + 15.0)
  This means at distance=15 growth is 50% of raw, at distance=30 it's 67%,
  at distance=5 it's 25%. Players can slightly exceed their cap via noise
  (soft cap) but the base curve never pushes past it.

  The cap is passed in per-call from player_talent_caps — skills grow
  toward a player-specific ceiling, not a global one. Two players with
  identical base stamina may have caps of 57 vs 73.

Career net delta targets (start=50, ages 17→38):
  Physical (SP/PO/AR/KK/ST/RE): net negative — retire below entry
  Coached  (EY/CT/BR/AC/BU):    net positive — craft improves over career
  Defense  (IF/OF/CA/GB):       roughly neutral to slightly negative
  Clutch   (CL):                random walk, near-zero net
"""

import random

# ═══════════════════════════════════════════════════════════════
#  AGING CURVE CONSTANTS
# ═══════════════════════════════════════════════════════════════

# ── Speed (SP) — physical, peaks 22-26, sharp fall after 30 ──
SP_PHASE_BREAKS = [22, 27, 31, 34]
SP_RATES = [0.8, 0.1, -0.9, -2.2, -2.8]
SP_NOISES = [1.5, 1.0, 0.8, 0.7, 0.6]

# ── Power (PO) — physical, slow rise then long plateau ──
PO_PHASE_BREAKS = [21, 29, 33]
PO_RATES = [0.8, 0.4, -0.4, -1.6]
PO_NOISES = [1.5, 1.0, 0.8, 0.7]

# ── Arm (AR) — physical, peaks mid-20s, declines from 30 ──
AR_PHASE_BREAKS = [24, 29, 33]
AR_RATES = [1.6, 0.2, -1.0, -1.8]
AR_NOISES = [0.5, 0.4, 0.5, 0.6]

# ── Strikeout (KK) — raw talent, can't be coached ──
KK_PHASE_BREAKS = [24, 28, 32]
KK_RATES = [1.8, 0.4, -0.6, -2.0]
KK_NOISES = [0.6, 0.5, 0.5, 0.7]

# ── Clutch (CL) — cognitive random walk, vet upward drift ──
CL_VET_AGE = 28
CL_VET_BONUS = 0.35
CL_NOISE = 1.6

# ── Eye (EY) — plate discipline, coaching-sensitive ──
EY_PHASE_BREAKS = [27, 33, 36]
EY_RATES = [1.3, 0.4, -0.4, -1.1]
EY_NOISES = [0.5, 0.4, 0.4, 0.5]
EY_COACHED = [True, True, False, False]

# ── Contact (CT) — trainable; very slow decline after mid-30s ──
CT_PHASE_BREAKS = [27, 34, 37]
CT_RATES = [1.2, 0.5, -0.3, -0.9]
CT_NOISES = [0.5, 0.4, 0.4, 0.4]
CT_COACHED = [True, True, False, False]

# ── Base Running (BR) — decision-making, never declines ──
BR_PHASE_BREAKS = [34]
BR_RATES = [0.9, 0.1]
BR_NOISES = [0.4, 0.3]
BR_COACHED = [True, True]

# ── Pitching Accuracy (AC) — asymptotes toward cap ──
AC_BASE_RATE = 0.8
AC_NOISE = 0.6

# ── Pitching Stamina (ST) — rises early, declines from 30+ ──
ST_PHASE_BREAKS = [26, 31, 34]
ST_RATES = [0.7, 0.3, -1.2, -2.0]
ST_NOISES = [1.5, 1.4, 1.5, 1.7]
ST_COACHED = [True, True, False, False]

# ── Pitching Recovery (RE) — most coaching-sensitive ──
RE_PHASE_BREAKS = [26, 31, 34]
RE_RATES = [1.3, 0.2, -1.3, -1.9]
RE_NOISES = [1.5, 1.4, 1.5, 1.7]
RE_COACHED = [True, True, False, False]

# ── Bunting (BU) — pure technique ──
BU_BASE_RATE = 0.2
BU_NOISE = 0.5

# ── Catching (CA) — experience-driven, physical wear after 32 ──
CA_DECLINE_AGE = 32
CA_BASE_RATE = 0.4
CA_BASE_NOISE = 0.5
CA_DECLINE_RATE = -0.8
CA_DECLINE_NOISE = 1.5

# ── Infield (IF) — technique + range; range declines after 30 ──
IF_DECLINE_AGE_LIGHT = 29
IF_DECLINE_AGE_HARD = 33
IF_RATE_GROWTH = 0.5
IF_NOISE_GROWTH = 0.6
IF_RATE_LIGHT = -0.3
IF_NOISE_LIGHT = 0.5
IF_RATE_HARD = -0.9
IF_NOISE_HARD = 0.6

# ── Outfield (OF) — range-dependent, declines earlier than infield ──
OF_DECLINE_AGE_LIGHT = 29
OF_DECLINE_AGE_HARD = 32
OF_RATE_GROWTH = 0.5
OF_NOISE_GROWTH = 0.5
OF_RATE_LIGHT = -0.4
OF_NOISE_LIGHT = 0.6
OF_RATE_HARD = -1.4
OF_NOISE_HARD = 0.7

# ── Ground Balls (GB) — pitcher physical skill, peaks mid-20s ──
GB_DECLINE_AGE_LIGHT = 28
GB_DECLINE_AGE_HARD = 32
GB_RATE_GROWTH = 0.55
GB_NOISE_GROWTH = 0.3
GB_RATE_LIGHT = -0.3
GB_NOISE_LIGHT = 0.4
GB_RATE_HARD = -1.2
GB_NOISE_HARD = 0.6

# ── Sigmoid dampening constant ──
# Controls how early growth slows near the cap.
# At distance=CAP_BRAKE: growth is 50% of raw.
# Smaller value = growth slows sooner.
CAP_BRAKE = 15.0


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────


def noise(rng: random.Random, scale: float = 1.0) -> float:
    """Standard normal noise scaled to ±scale (68% of values)."""
    return rng.gauss(0, scale)


def _cap_dampen(raw: float, val: float, cap: int | None) -> float:
    """
    Apply sigmoid dampening as value approaches its talent cap.

    For positive deltas only. Negative deltas (decline phases) pass through
    unchanged — players don't stop declining just because they're near their cap.

    Formula: dampened = raw * distance / (distance + CAP_BRAKE)
    At distance=0 (at cap): returns 0.0 (soft stop)
    At distance=CAP_BRAKE:  returns raw * 0.5
    At distance=large:      approaches raw (no dampening far from cap)

    Args:
        raw: Undampened delta
        val: Current skill value
        cap: Per-player talent cap, or None (no dampening applied)

    Returns:
        Dampened delta
    """
    if raw <= 0 or cap is None:
        return raw
    distance = max(0.0, cap - val)
    if distance <= 0:
        return 0.0
    return raw * (distance / (distance + CAP_BRAKE))


# ─────────────────────────────────────────────
#  SKILL AGING
# ─────────────────────────────────────────────


class SkillAging:

    def phased_delta(
        self,
        age: int,
        val: float,
        rng: random.Random,
        breaks: list[int],
        rates: list[float],
        noises: list[float],
        coached: list[bool] | None = None,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """
        Resolve the age phase and return rate + noise, optionally scaled
        by the coaching multiplier when coached[phase] is True.

        Phase breaks must be in ascending order. The phase fires when
        age < break. The final rate/noise applies for all remaining ages.

        Positive deltas are dampened as val approaches the per-player cap.
        Negative deltas are never dampened.

        Args:
            age:      Player's current age
            val:      Current skill value
            rng:      Seeded RNG
            breaks:   Phase transition ages (ascending)
            rates:    Base rate per phase
            noises:   Noise sigma per phase
            coached:  Whether each phase responds to coaching
            coaching: Coaching quality multiplier (1.0 = neutral)
            cap:      Per-player talent cap (None = no dampening)
        """
        idx = len(breaks)
        for i, b in enumerate(breaks):
            if age < b:
                idx = i
                break

        raw = rates[idx] + noise(rng, noises[idx])
        if coached and coached[idx]:
            raw = coaching * raw

        return _cap_dampen(raw, val, cap)

    # ─────────────────────────────────────────────
    #  AGING DELTAS
    # ─────────────────────────────────────────────

    def delta_SP(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Run Speed — physical, peaks 22-26, sharp fall after 30."""
        return self.phased_delta(
            age, val, rng, SP_PHASE_BREAKS, SP_RATES, SP_NOISES, cap=cap
        )

    def delta_PO(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Batting Power — slow rise, long plateau, late decline."""
        return self.phased_delta(
            age, val, rng, PO_PHASE_BREAKS, PO_RATES, PO_NOISES, cap=cap
        )

    def delta_AR(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Throwing Arm — physical, peaks mid-20s, declines from 30."""
        return self.phased_delta(
            age, val, rng, AR_PHASE_BREAKS, AR_RATES, AR_NOISES, cap=cap
        )

    def delta_KK(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Strikeout ability — raw talent, can't be coached."""
        return self.phased_delta(
            age, val, rng, KK_PHASE_BREAKS, KK_RATES, KK_NOISES, cap=cap
        )

    @staticmethod
    def delta_CL(
        age: int, val: float, rng: random.Random, playoff_boost: float = 0.0
    ) -> float:
        """Clutch — cognitive random walk with vet upward drift."""
        vet_bonus = CL_VET_BONUS if age >= CL_VET_AGE else 0.0
        return vet_bonus + playoff_boost + noise(rng, CL_NOISE)

    def delta_EY(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Eye / plate discipline — peaks later than physical, coaching-sensitive."""
        return self.phased_delta(
            age,
            val,
            rng,
            EY_PHASE_BREAKS,
            EY_RATES,
            EY_NOISES,
            EY_COACHED,
            coaching,
            cap=cap,
        )

    def delta_CT(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Contact — trainable; very slow decline after mid-30s."""
        return self.phased_delta(
            age,
            val,
            rng,
            CT_PHASE_BREAKS,
            CT_RATES,
            CT_NOISES,
            CT_COACHED,
            coaching,
            cap=cap,
        )

    def delta_BR(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Base running — decision-making, never declines."""
        return self.phased_delta(
            age,
            val,
            rng,
            BR_PHASE_BREAKS,
            BR_RATES,
            BR_NOISES,
            BR_COACHED,
            coaching,
            cap=cap,
        )

    @staticmethod
    def delta_AC(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Pitching accuracy — asymptotically approaches cap."""
        raw = coaching * (AC_BASE_RATE + noise(rng, AC_NOISE))
        raw = max(0.0, raw)
        return _cap_dampen(raw, val, cap)

    def delta_ST(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Pitching stamina — rises early, declines from 30+."""
        return self.phased_delta(
            age,
            val,
            rng,
            ST_PHASE_BREAKS,
            ST_RATES,
            ST_NOISES,
            ST_COACHED,
            coaching,
            cap=cap,
        )

    def delta_RE(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Pitching recovery — most coaching-sensitive; declines from 30+."""
        return self.phased_delta(
            age,
            val,
            rng,
            RE_PHASE_BREAKS,
            RE_RATES,
            RE_NOISES,
            RE_COACHED,
            coaching,
            cap=cap,
        )

    @staticmethod
    def delta_BU(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Bunting — pure technique, never declines."""
        raw = max(0.0, coaching * (BU_BASE_RATE + noise(rng, BU_NOISE)))
        return _cap_dampen(raw, val, cap)

    @staticmethod
    def delta_CA(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Catching — experience-driven, physical wear after decline age."""
        if age > CA_DECLINE_AGE:
            return CA_DECLINE_RATE + noise(rng, CA_DECLINE_NOISE)
        raw = max(0.0, coaching * (CA_BASE_RATE + noise(rng, CA_BASE_NOISE)))
        return _cap_dampen(raw, val, cap)

    @staticmethod
    def delta_IF(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Infield — technique + range; range declines after 30."""
        if age > IF_DECLINE_AGE_HARD:
            return IF_RATE_HARD + noise(rng, IF_NOISE_HARD)
        if age > IF_DECLINE_AGE_LIGHT:
            return IF_RATE_LIGHT + noise(rng, IF_NOISE_LIGHT)
        raw = max(0.0, coaching * (IF_RATE_GROWTH + noise(rng, IF_NOISE_GROWTH)))
        return _cap_dampen(raw, val, cap)

    @staticmethod
    def delta_OF(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Outfield — range-dependent, declines earlier than infield."""
        if age > OF_DECLINE_AGE_HARD:
            return OF_RATE_HARD + noise(rng, OF_NOISE_HARD)
        if age > OF_DECLINE_AGE_LIGHT:
            return OF_RATE_LIGHT + noise(rng, OF_NOISE_LIGHT)
        raw = max(0.0, coaching * (OF_RATE_GROWTH + noise(rng, OF_NOISE_GROWTH)))
        return _cap_dampen(raw, val, cap)

    @staticmethod
    def delta_GB(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Ground balls — pitcher physical skill, peaks mid-20s, declines from 30."""
        if age > GB_DECLINE_AGE_HARD:
            return GB_RATE_HARD + noise(rng, GB_NOISE_HARD)
        if age > GB_DECLINE_AGE_LIGHT:
            return GB_RATE_LIGHT + noise(rng, GB_NOISE_LIGHT)
        raw = max(0.0, coaching * (GB_RATE_GROWTH + noise(rng, GB_NOISE_GROWTH)))
        return _cap_dampen(raw, val, cap)
