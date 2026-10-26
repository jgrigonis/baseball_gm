# src/player/player_skill_aging.py
"""
Player Skill Aging

Each delta function returns the expected one-year change in a skill.
Constants are grouped by skill above each function for easy tuning.

Phase breaks are always ascending. phased_delta() resolves the phase
using age < break, so the last rate/noise applies for all remaining ages.

Growth is spread from 17 through about 27, so a player drafted at 18-22
still has most of his development ahead of him. Physical tools (speed,
arm) level off a little earlier; craft skills keep creeping up into the
early 30s.

Ceiling dampening (per-player soft caps):
  The phase rate slows as a player approaches their talent cap:
      dampening = distance / (distance + CAP_BRAKE)
  Only the rate is dampened, never the noise, so a player sitting at his
  cap random-walks around it instead of drifting below it. Players can
  exceed their cap via noise (soft cap) but the base curve never pushes
  past it.

  The cap is passed in per-call from player_talent_caps — skills grow
  toward a player-specific ceiling, not a global one. Caps are sized from
  planned_growth() (the total growth these curves call for), so the curve,
  not the cap, decides when a player peaks.

Career net delta targets (ages 17→38):
  Physical (SP/PO/AR/KK/ST/RE/DU): net small — retire near or below entry
  Coached  (EY/CT/BR/AC/BU):       net positive — craft improves over career
  Defense  (IF/OF/CA/GB):          net positive, fading in the 30s
  Clutch   (CL):                   noisy, slight upward drift for veterans
"""

import random

# ═══════════════════════════════════════════════════════════════
#  AGING CURVE CONSTANTS
# ═══════════════════════════════════════════════════════════════

# ── Speed (SP) — physical, peaks 23-27, sharp fall after 30 ──
SP_PHASE_BREAKS = [24, 28, 31, 34, 39]
SP_RATES = [0.8, 0.0, -0.9, -2.2, -2.8, -4.5]
SP_NOISES = [1.0, 0.8, 0.8, 0.7, 0.6, 1.9]

# ── Power (PO) — physical, steady rise to 27, plateau, late decline ──
PO_PHASE_BREAKS = [28, 32, 35]
PO_RATES = [1.6, 0.3, -0.6, -2.1]
PO_NOISES = [1.2, 0.8, 0.7, 0.8]

# ── Arm (AR) — physical, rises to the mid-20s, declines from 30 ──
AR_PHASE_BREAKS = [26, 30, 33]
AR_RATES = [1.2, 0.2, -1.0, -1.9]
AR_NOISES = [0.8, 0.4, 0.5, 0.6]

# ── Strikeout (KK) — raw talent, can't be coached ──
KK_PHASE_BREAKS = [28, 31, 34]
KK_RATES = [1.5, 0.3, -0.9, -2.1]
KK_NOISES = [0.6, 0.5, 0.5, 1.7]

# ── Clutch (CL) — cognitive random walk, vet upward drift ──
CL_VET_AGE_BREAKS = [28, 34]  # phase boundaries
CL_VET_BONUSES = [0.4, 0.6, 0.8]  # under 28 | 28-33 | 34+
CL_NOISE = 2.0

# ── Eye (EY) — plate discipline, coaching-sensitive ──
EY_PHASE_BREAKS = [28, 33, 36]
EY_RATES = [2.0, 0.6, -0.4, -1.3]
EY_NOISES = [0.6, 0.6, 0.6, 0.5]
EY_COACHED = [True, True, False, False]

# ── Contact (CT) — trainable; very slow decline after mid-30s ──
CT_PHASE_BREAKS = [28, 34, 37]
CT_RATES = [2.0, 0.5, -0.3, -1.4]
CT_NOISES = [0.7, 0.5, 0.4, 0.4]
CT_COACHED = [True, True, False, False]

# ── Base Running (BR) — decision-making, never declines until late ──
BR_PHASE_BREAKS = [28, 34, 38]
BR_RATES = [1.5, 0.5, 0.0, -0.9]
BR_NOISES = [0.4, 0.3, 0.3, 0.5]
BR_COACHED = [True, True, False, False]

# ── Pitching Accuracy (AC) — keeps improving, declines after 36 ──
AC_PHASE_BREAKS = [29, 36]
AC_RATES = [1.5, 0.4, -0.8]
AC_NOISES = [0.6, 0.5, 0.8]
AC_COACHED = [True, True, False]

# ── Pitching Stamina (ST) — rises to the late 20s, declines from 31 ──
ST_PHASE_BREAKS = [28, 31, 34]
ST_RATES = [1.0, 0.2, -1.2, -2.0]
ST_NOISES = [0.9, 0.8, 1.2, 1.5]
ST_COACHED = [True, True, False, False]

# ── Pitching Recovery (RE) — most coaching-sensitive ──
RE_PHASE_BREAKS = [28, 31, 34]
RE_RATES = [1.3, 0.4, -1.3, -1.9]
RE_NOISES = [1.0, 1.0, 1.5, 1.7]
RE_COACHED = [True, True, False, False]

# ── Bunting (BU) — pure technique, very slow decline after 40 ──
BU_PHASE_BREAKS = [40]
BU_RATES = [0.5, -0.4]
BU_NOISES = [0.5, 0.5]
BU_COACHED = [True, False]

# ── Catching (CA) — experience-driven, physical wear after 32 ──
CA_PHASE_BREAKS = [28, 33]
CA_RATES = [1.2, 0.3, -0.8]
CA_NOISES = [0.5, 0.5, 1.5]
CA_COACHED = [True, True, False]

# ── Infield (IF) — technique + range; range declines after 30 ──
IF_PHASE_BREAKS = [28, 31, 34]
IF_RATES = [1.5, 0.2, -0.3, -0.9]
IF_NOISES = [0.6, 0.5, 0.5, 0.6]
IF_COACHED = [True, True, False, False]

# ── Outfield (OF) — range-dependent, declines earlier than infield ──
OF_PHASE_BREAKS = [28, 30, 33]
OF_RATES = [1.5, 0.0, -0.4, -1.4]
OF_NOISES = [0.5, 0.5, 0.6, 0.7]
OF_COACHED = [True, False, False, False]

# ── Ground Balls (GB) — pitcher skill, rises to the late 20s ──
GB_PHASE_BREAKS = [29, 33]
GB_RATES = [1.1, -0.3, -1.2]
GB_NOISES = [0.3, 0.4, 0.6]
GB_COACHED = [True, False, False]

# ── Durability (DU) — general physical skill, peaks late-20s ──
DU_PHASE_BREAKS = [28, 31, 37]
DU_RATES = [1.2, 0.2, -0.3, -2.8]
DU_NOISES = [0.3, 0.3, 0.4, 0.6]
DU_COACHED = [True, True, False, False]

# Full skill name → (phase breaks, phase rates), used by planned_growth().
SKILL_CURVES: dict[str, tuple[list[int], list[float]]] = {
    "speed": (SP_PHASE_BREAKS, SP_RATES),
    "power": (PO_PHASE_BREAKS, PO_RATES),
    "arm": (AR_PHASE_BREAKS, AR_RATES),
    "strikes": (KK_PHASE_BREAKS, KK_RATES),
    "clutch": (CL_VET_AGE_BREAKS, CL_VET_BONUSES),
    "eye": (EY_PHASE_BREAKS, EY_RATES),
    "contact": (CT_PHASE_BREAKS, CT_RATES),
    "base_running": (BR_PHASE_BREAKS, BR_RATES),
    "accuracy": (AC_PHASE_BREAKS, AC_RATES),
    "stamina": (ST_PHASE_BREAKS, ST_RATES),
    "recovery": (RE_PHASE_BREAKS, RE_RATES),
    "bunting": (BU_PHASE_BREAKS, BU_RATES),
    "catching": (CA_PHASE_BREAKS, CA_RATES),
    "infield": (IF_PHASE_BREAKS, IF_RATES),
    "outfield": (OF_PHASE_BREAKS, OF_RATES),
    "ground_balls": (GB_PHASE_BREAKS, GB_RATES),
    "durability": (DU_PHASE_BREAKS, DU_RATES),
}

# Ages planned_growth() sums over: START_AGE through a long career.
PLANNED_GROWTH_AGES = range(17, 40)

# ── Sigmoid dampening constant ──
# Controls how early growth slows near the cap.
# At distance=CAP_BRAKE: growth is 50% of raw.
# Smaller value = growth slows LATER (only near the ceiling).
# Larger value = growth slows SOONER (dampening kicks in further from cap).
CAP_BRAKE = 2.0


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────


def noise(rng: random.Random, scale: float = 1.0) -> float:
    """Standard normal noise scaled to ±scale (68% of values)."""
    return rng.gauss(0, scale)


def _phase_index(age: int, breaks: list[int]) -> int:
    """Index of the phase *age* falls in: the first break it is under."""
    for i, b in enumerate(breaks):
        if age < b:
            return i
    return len(breaks)


def planned_growth(skill: str) -> float:
    """
    Total growth the aging curve calls for over a career: the sum of the
    positive yearly rates from 17 through PLANNED_GROWTH_AGES. Talent caps
    are sized from this, so the curve and the cap agree.
    """
    breaks, rates = SKILL_CURVES[skill]
    return sum(
        max(0.0, rates[_phase_index(age, breaks)]) for age in PLANNED_GROWTH_AGES
    )


def _cap_dampen(raw: float, val: float, cap: int | None) -> float:
    """
    Apply sigmoid dampening to a phase rate as value approaches its talent cap.

    Callers pass the rate, not rate + noise: noise is added afterwards so it
    stays symmetric at the cap.

    For positive rates only. Negative rates (decline phases) pass through
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
        Resolve the age phase and return rate + noise. The rate is scaled
        by the coaching multiplier when coached[phase] is True.

        Phase breaks must be in ascending order. The phase fires when
        age < break. The final rate/noise applies for all remaining ages.

        A positive rate is dampened as val approaches the per-player cap.
        Negative rates and the noise are never dampened.

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
        idx = _phase_index(age, breaks)

        rate = rates[idx]
        if coached and coached[idx]:
            rate = coaching * rate

        return _cap_dampen(rate, val, cap) + noise(rng, noises[idx])

    # ─────────────────────────────────────────────
    #  AGING DELTAS
    # ─────────────────────────────────────────────

    def delta_SP(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Run Speed — physical, peaks 23-27, sharp fall after 30."""
        return self.phased_delta(
            age, val, rng, SP_PHASE_BREAKS, SP_RATES, SP_NOISES, cap=cap
        )

    def delta_PO(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Batting Power — steady rise to 27, plateau, late decline."""
        return self.phased_delta(
            age, val, rng, PO_PHASE_BREAKS, PO_RATES, PO_NOISES, cap=cap
        )

    def delta_AR(
        self, age: int, val: float, rng: random.Random, cap: int | None = None
    ) -> float:
        """Throwing Arm — physical, rises to the mid-20s, declines from 30."""
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
        idx = _phase_index(age, CL_VET_AGE_BREAKS)
        rate = CL_VET_BONUSES[idx] + playoff_boost
        return _cap_dampen(rate, val, cap) + noise(rng, CL_NOISE)

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
        """Pitching stamina — rises to the late 20s, declines from 31."""
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
        """Ground balls — pitcher skill, rises to the late 20s."""
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
