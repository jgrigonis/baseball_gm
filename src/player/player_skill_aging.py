# src/player/player_skill_aging.py

"""
Player Skill Aging
"""

import random

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────


def noise(rng: random.Random, scale: float = 1.0) -> float:
    """
    random.gauss(0, scale) draws a single random number from a
    normal (bell curve) distribution centered at 0 with a standard
    deviation of scale. In plain terms:

    It returns a small positive or negative float, most of the
    time close to zero
    The bigger scale is, the wider the spread of possible values
    With scale=1.0, about 68% of calls return something between
    -1.0 and +1.0, and about 95% land between -2.0 and +2.0

    So when you write something like return 1.2 + noise(0.5),
    you're saying "grow by roughly 1.2 this year, but add a
    realistic random wobble so no two careers are identical."
    Without it, every player aged identically.

    """
    return rng.gauss(0, scale)


class SkillAging:
    # ─────────────────────────────────────────────
    #  AGING DELTAS (one year)
    #  Each function returns the raw float delta
    #  to apply to a skill value.
    # ─────────────────────────────────────────────

    @staticmethod
    def delta_SP(age: int, val: float, rng: random.Random) -> float:
        """Run Speed — physical, peaks 22-26, sharp fall after 30."""
        if age < 22:
            return 1.2 + noise(rng, 0.5)
        elif age <= 26:
            return 0.1 + noise(rng, 0.4)
        elif age <= 30:
            return -0.9 + noise(rng, 0.5)
        elif age <= 33:
            return -2.2 + noise(rng, 0.6)
        else:
            return -2.8 + noise(rng, 0.7)

    @staticmethod
    def delta_PO(age: int, val: float, rng: random.Random) -> float:
        """Batting Power — physical, slow rise > long plateau > late decline."""
        if age < 21:
            return 2.0 + noise(rng, 0.7)
        elif age <= 28:
            return 0.7 + noise(rng, 0.5)
        elif age <= 32:
            return -0.2 + noise(rng, 0.5)
        else:
            return -1.6 + noise(rng, 0.7)

    @staticmethod
    def delta_AR(age: int, val: float, rng: random.Random) -> float:
        """Throwing Arm — physical, peaks mid-20s, declines from 30."""
        if age < 24:
            return 1.6 + noise(rng, 0.5)
        elif age <= 28:
            return 0.2 + noise(rng, 0.4)
        elif age <= 32:
            return -1.0 + noise(rng, 0.5)
        else:
            return -1.8 + noise(rng, 0.6)

    @staticmethod
    def delta_KK(age: int, val: float, rng: random.Random) -> float:
        """Strikeout ability — physical/raw talent, can't be coached."""
        if age < 24:
            return 1.8 + noise(rng, 0.6)
        elif age <= 27:
            return 0.4 + noise(rng, 0.5)
        elif age <= 31:
            return -0.6 + noise(rng, 0.5)
        else:
            return -2.0 + noise(rng, 0.7)

    @staticmethod
    def delta_CL(
        age: int, val: float, rng: random.Random, playoff_boost: float = 0.0
    ) -> float:
        """Clutch — cognitive, slight random walk, vet upward drift."""
        vet_bonus = 0.35 if age >= 28 else 0.0
        return vet_bonus + playoff_boost + noise(rng, 1.6)

    @staticmethod
    def delta_EY(
        age: int, val: float, rng: random.Random, coaching: float = 1.0
    ) -> float:
        """Eye / plate discipline — peaks later than physical, gentle decline."""
        if age < 27:
            return coaching * (1.3 + noise(rng, 0.5))
        elif age <= 32:
            return coaching * (0.4 + noise(rng, 0.4))
        elif age <= 35:
            return -0.4 + noise(rng, 0.4)
        else:
            return -1.1 + noise(rng, 0.5)

    @staticmethod
    def delta_CT(
        age: int, val: float, rng: random.Random, coaching: float = 1.0
    ) -> float:
        """Contact — trainable; very slow decline after mid-30s."""
        if age < 27:
            return coaching * (1.2 + noise(rng, 0.5))
        elif age <= 33:
            return coaching * (0.5 + noise(rng, 0.4))
        elif age <= 36:
            return -0.3 + noise(rng, 0.4)
        else:
            return -0.9 + noise(rng, 0.4)

    @staticmethod
    def delta_BR(
        age: int, val: float, rng: random.Random, coaching: float = 1.0
    ) -> float:
        """Base running — decision-making, trends up all career, late plateau."""
        if age <= 33:
            return coaching * (0.9 + noise(rng, 0.4))
        else:
            return coaching * (0.1 + noise(rng, 0.3))  # plateau, not decline

    @staticmethod
    def delta_technical_up(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        slow_after: int = 33,
    ) -> float:
        """Generic always-upward technical skill (BU, CA, IF, OF, GB)."""
        rate = coaching * (0.8 + noise(rng, 0.4))
        if age > slow_after:
            rate *= 0.45  # slows but never negative by design
        return max(0.0, rate)

    @staticmethod
    def delta_AC(
        age: int,
        val: float,
        rng: random.Random,
        coaching: float = 1.0,
        ceiling: int = 90,
    ) -> float:
        """Pitching accuracy — asymptotically approaches player ceiling."""
        distance = max(0.0, ceiling - val)
        base = coaching * (0.55 + noise(rng, 0.3)) * (distance / 45.0)
        return max(0.0, base)

    @staticmethod
    def delta_ST(
        age: int, val: float, rng: random.Random, coaching: float = 1.0
    ) -> float:
        """Pitching stamina — rises early, declines from 30+."""
        if age < 26:
            return coaching * (1.1 + noise(rng, 0.5))
        elif age <= 30:
            return coaching * (0.3 + noise(rng, 0.4))
        elif age <= 33:
            return -1.0 + noise(rng, 0.5)
        else:
            return -2.0 + noise(rng, 0.7)

    @staticmethod
    def delta_RE(
        age: int, val: float, rng: random.Random, coaching: float = 1.0
    ) -> float:
        """Pitching recovery — most coaching-sensitive; declines from 30+."""
        if age < 26:
            return coaching * (1.3 + noise(rng, 0.5))
        elif age <= 30:
            return coaching * (0.5 + noise(rng, 0.4))
        elif age <= 33:
            return -0.8 + noise(rng, 0.5)
        else:
            return -1.7 + noise(rng, 0.7)


    @staticmethod
    def delta_BU(age, val, rng: random.Random, coaching: float = 1.0, ceiling=75):
        """Bunting — pure technique, low ceiling, never declines."""
        distance = max(0.0, ceiling - val)
        return max(0.0, coaching * (0.4 + noise(rng, 0.3)) * (distance / 40.0))


    @staticmethod
    def delta_CA(age, val, rng: random.Random, coaching: float = 1.0, ceiling=88):
        """Catching — experience-driven, peaks 28-32, physical wear after."""
        distance = max(0.0, ceiling - val)
        if age > 32:
            return -0.6 + noise(rng, 0.5)
        return max(0.0, coaching * (0.6 + noise(rng, 0.3)) * (distance / 40.0))


    @staticmethod
    def delta_IF(age, val, rng: random.Random, coaching: float = 1.0, ceiling=85):
        """Infield — technique + range; range declines after 30."""
        distance = max(0.0, ceiling - val)
        if age > 33:
            return -0.8 + noise(rng, 0.5)
        elif age > 30:
            return -0.2 + noise(rng, 0.4)
        return max(0.0, coaching * (0.5 + noise(rng, 0.3)) * (distance / 40.0))


    @staticmethod
    def delta_OF(age, val, rng: random.Random, coaching: float = 1.0, ceiling=85):
        """Outfield — range-dependent, declines earlier than infield."""
        distance = max(0.0, ceiling - val)
        if age > 32:
            return -1.0 + noise(rng, 0.5)
        elif age > 29:
            return -0.3 + noise(rng, 0.4)
        return max(0.0, coaching * (0.5 + noise(rng, 0.3)) * (distance / 40.0))


    @staticmethod
    def delta_GB(age, val, rng: random.Random, coaching: float = 1.0, ceiling=83):
        """Ground balls — pitcher physical skill, peaks mid-20s, declines from 30."""
        distance = max(0.0, ceiling - val)
        if age > 32:
            return -1.2 + noise(rng, 0.6)
        elif age > 28:
            return -0.3 + noise(rng, 0.4)
        return max(0.0, coaching * (0.55 + noise(rng, 0.3)) * (distance / 40.0))
