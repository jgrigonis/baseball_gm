# src/player/player_skill_aging.py
"""
Player Skill Aging

Each delta function returns the expected one-year change in a skill.
Constants are grouped by skill above each function for easy tuning.

Phase breaks are always ascending. phased_delta() resolves the phase
using age < break, so the last rate/noise applies for all remaining ages.

Ceiling dampening (per-player soft caps):
  Growth slows as a player approaches their talent cap using a sigmoid:
      dampening = distance / (distance + 4.0)
  This means at distance=4 growth is 50% of raw, at distance=8 it's 67%,
  at distance=1 it's 25%. Players can slightly exceed their cap via noise
  (soft cap) but the base curve never pushes past it.

  The cap is passed in per-call from player_talent_caps — skills grow
  toward a player-specific ceiling, not a global one. Two players with
  identical base stamina may have caps of 57 vs 73.

Career net delta targets (start=50, ages 17→38):
  Physical (SP/PO/AR/KK/ST/RE/DU): net negative — retire below entry
  Coached  (EY/CT/BR/AC/BU):       net positive — craft improves over career
  Defense  (IF/OF/CA/GB):          roughly neutral to slightly negative
  Clutch   (CL):                   random walk, near-zero net
"""

import random

# ═══════════════════════════════════════════════════════════════
#  AGING CURVE CONSTANTS
# ═══════════════════════════════════════════════════════════════

# ── Speed (SP) — physical, peaks 22-26, sharp fall after 30 ──
SP_PHASE_BREAKS = [22, 27, 31, 34, 39]
SP_RATES = [0.9, 0.1, -0.9, -2.2, -2.8, -4.5]
SP_NOISES = [1.8, 1.0, 0.8, 0.7, 0.6, 1.9]

# ── Power (PO) — physical, slow rise then long plateau ──
PO_PHASE_BREAKS = [21, 29, 33, 36]
PO_RATES = [2.6, 0.9, 0.6, -0.6, -2.1]
PO_NOISES = [2.0, 1.2, 0.8, 0.7, 0.8]

# ── Arm (AR) — physical, peaks mid-20s, declines from 30 ──
AR_PHASE_BREAKS = [24, 29, 33]
AR_RATES = [1.9, 0.4, -1.0, -1.9]
AR_NOISES = [0.8, 0.4, 0.5, 0.6]

# ── Strikeout (KK) — raw talent, can't be coached ──
KK_PHASE_BREAKS = [24, 30, 34]
KK_RATES = [1.9, 1.1, -0.9, -2.1]
KK_NOISES = [0.6, 0.5, 0.5, 1.7]

# ── Clutch (CL) — cognitive random walk, vet upward drift ──
CL_VET_AGE_BREAKS = [28, 34]  # phase boundaries
CL_VET_BONUSES = [0.5, 1.4, 1.9]  # under 28 | 28-33 | 34+
CL_NOISE = 3.5

# ── Eye (EY) — plate discipline, coaching-sensitive ──
EY_PHASE_BREAKS = [27, 33, 36]
EY_RATES = [2.9, 1.5, -0.4, -1.3]
EY_NOISES = [0.5, 0.6, 0.6, 0.5]
EY_COACHED = [True, True, False, False]

# ── Contact (CT) — trainable; very slow decline after mid-30s ──
CT_PHASE_BREAKS = [27, 34, 37]
CT_RATES = [2.5, 1.1, -0.3, -1.4]
CT_NOISES = [0.7, 0.5, 0.4, 0.4]
CT_COACHED = [True, True, False, False]

# ── Base Running (BR) — decision-making, never declines ──
BR_PHASE_BREAKS = [34, 38]
BR_RATES = [1.8, 0.3, -0.9]
BR_NOISES = [0.4, 0.3, 0.5]
BR_COACHED = [True, True, False]

# ── Pitching Accuracy (AC) — declines after 36 ──
AC_PHASE_BREAKS = [36]
AC_RATES = [1.6, -0.8]
AC_NOISES = [0.6, 0.8]
AC_COACHED = [True, False]

# ── Pitching Stamina (ST) — rises early, declines from 30+ ──
ST_PHASE_BREAKS = [26, 31, 34]
ST_RATES = [0.9, 0.3, -1.2, -2.0]
ST_NOISES = [0.9, 0.8, 1.2, 1.5]  # was [1.5, 1.4, 1.5, 1.7]
ST_COACHED = [True, True, False, False]

# ── Pitching Recovery (RE) — most coaching-sensitive ──
RE_PHASE_BREAKS = [26, 31, 34]
RE_RATES = [1.6, 0.9, -1.3, -1.9]
RE_NOISES = [1.5, 1.4, 1.5, 1.7]
RE_COACHED = [True, True, False, False]

# ── Bunting (BU) — pure technique, very slow decline after 40 ──
BU_PHASE_BREAKS = [40]
BU_RATES = [0.5, -0.4]
BU_NOISES = [0.5, 0.5]
BU_COACHED = [True, False]

# ── Catching (CA) — experience-driven, physical wear after 32 ──
CA_PHASE_BREAKS = [33]
CA_RATES = [0.7, -0.8]
CA_NOISES = [0.5, 1.5]
CA_COACHED = [True, False]

# ── Infield (IF) — technique + range; range declines after 30 ──
IF_PHASE_BREAKS = [30, 34]
IF_RATES = [1.9, -0.3, -0.9]
IF_NOISES = [0.6, 0.5, 0.6]
IF_COACHED = [True, False, False]

# ── Outfield (OF) — range-dependent, declines earlier than infield ──
OF_PHASE_BREAKS = [30, 33]
OF_RATES = [1.9, -0.4, -1.4]
OF_NOISES = [0.5, 0.6, 0.7]
OF_COACHED = [True, False, False]

# ── Ground Balls (GB) — pitcher physical skill, peaks mid-20s ──
GB_PHASE_BREAKS = [29, 33]
GB_RATES = [1.1, -0.3, -1.2]
GB_NOISES = [0.3, 0.4, 0.6]
GB_COACHED = [True, False, False]

# ── Durability (DU) — general physical skill, peaks late-20s ──
DU_PHASE_BREAKS = [31, 37]
DU_RATES = [1.9, -0.3, -2.8]
DU_NOISES = [0.3, 0.4, 0.6]
DU_COACHED = [True, False, False]

# ── Sigmoid dampening constant ──
# Controls how early growth slows near the cap.
# At distance=CAP_BRAKE: growth is 50% of raw.
# Smaller value = growth slows LATER (only near the ceiling).
# Larger value = growth slows SOONER (dampening kicks in further from cap).
CAP_BRAKE = 4.0


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

    note: coached=False on decline phases is always irrelevant

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
    def delta_CL(age, val, rng, cap=None, playoff_boost=0.0) -> float:
        idx = len(CL_VET_AGE_BREAKS)
        for i, break_age in enumerate(CL_VET_AGE_BREAKS):
            if age < break_age:
                idx = i
                break
        raw = CL_VET_BONUSES[idx] + playoff_boost + noise(rng, CL_NOISE)
        return _cap_dampen(raw, val, cap)

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
        """Base running — decision-making, declines after 38."""
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

    def delta_AC(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Pitching accuracy — eventually declines."""
        return self.phased_delta(
            age,
            val,
            rng,
            AC_PHASE_BREAKS,
            AC_RATES,
            AC_NOISES,
            AC_COACHED,
            coaching,
            cap=cap,
        )

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

    def delta_BU(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Bunting — pure technique, declines after 40."""
        return self.phased_delta(
            age,
            val,
            rng,
            BU_PHASE_BREAKS,
            BU_RATES,
            BU_NOISES,
            BU_COACHED,
            coaching,
            cap=cap,
        )

    def delta_CA(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Catching — experience-driven, physical wear after 32."""
        return self.phased_delta(
            age,
            val,
            rng,
            CA_PHASE_BREAKS,
            CA_RATES,
            CA_NOISES,
            CA_COACHED,
            coaching,
            cap=cap,
        )

    def delta_IF(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Infield — technique + range; declines from 30."""
        return self.phased_delta(
            age,
            val,
            rng,
            IF_PHASE_BREAKS,
            IF_RATES,
            IF_NOISES,
            IF_COACHED,
            coaching,
            cap=cap,
        )

    def delta_OF(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Outfield — range-dependent, declines earlier than infield."""
        return self.phased_delta(
            age,
            val,
            rng,
            OF_PHASE_BREAKS,
            OF_RATES,
            OF_NOISES,
            OF_COACHED,
            coaching,
            cap=cap,
        )

    def delta_GB(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Ground balls — pitcher physical skill, peaks mid-20s."""
        return self.phased_delta(
            age,
            val,
            rng,
            GB_PHASE_BREAKS,
            GB_RATES,
            GB_NOISES,
            GB_COACHED,
            coaching,
            cap=cap,
        )

    def delta_DU(
        self,
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        cap: int | None = None,
    ) -> float:
        """Durability — physical skill, peaks late-20s, hard decline after 36."""
        return self.phased_delta(
            age,
            val,
            rng,
            DU_PHASE_BREAKS,
            DU_RATES,
            DU_NOISES,
            DU_COACHED,
            coaching,
            cap=cap,
        )
