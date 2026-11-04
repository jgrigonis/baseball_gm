# src/player/contracts.py
"""
Player contracts.

Everyone on a team (26-man, 40-man or minors) plays under a contract: a
salary paid each season for a run of seasons. There are two kinds.

- Rookie deals. A drafted player signs one the season he's drafted: three
  seasons at a salary set by where he was picked. Early picks get more, as
  they do with real signing bonuses, which are folded into the salary here.
  It runs its three years whether or not he keeps his rookie (r).
- Standard deals. Everyone else, priced from how good he is (his overall
  grade on the pro curve) and how old he is. Stars get longer deals, old
  players and fringe players short ones.

A deal that runs out is re-signed at the player's new value until free agency
exists. A league's starting rosters get standard deals already partway
through, so they don't all run out the same winter.

Pure rules only; src/db/repositories/contract_repo.py reads and writes them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.api.grade_curves import GRADES, OVERALL_CUTOFFS

# The MLB minimum salary.
MIN_SALARY = 780_000
# Nobody is paid more than this a season.
MAX_SALARY = 40_000_000

ROOKIE_YEARS = 3

# What a player in his prime is paid each season at each grade, A+ to F.
# Shaped like MLB free agent pay: a handful of $30M stars, a B a solid
# regular, a C a bench player near the minimum.
GRADE_SALARY: dict[str, int] = {
    "A+": 32_000_000,
    "A": 25_000_000,
    "A-": 19_000_000,
    "B+": 14_000_000,
    "B": 10_000_000,
    "B-": 7_000_000,
    "C+": 4_500_000,
    "C": 2_800_000,
    "C-": 1_700_000,
    "D+": 1_100_000,
    "D": 850_000,
    "D-": MIN_SALARY,
    "F": MIN_SALARY,
}

# The first pick's signing bonus. Each later pick's is a bit smaller, as on
# MLB's slot scale, and a rookie's salary is the minimum plus a third of it.
TOP_PICK_BONUS = 10_000_000
BONUS_DECAY_PICKS = 12  # the bonus falls by about 1/e every 12 picks

# A standard deal's salary moves this much either way at random, so two
# players with the same grade and age don't sign the same deal.
SALARY_NOISE = 0.10


@dataclass(frozen=True)
class Deal:
    salary: int
    years: int
    kind: str  # 'rookie' or 'standard'


def round_salary(amount: float) -> int:
    """Round to $10K under $1M, $50K above, inside the min and max."""
    amount = max(MIN_SALARY, min(MAX_SALARY, amount))
    step = 10_000 if amount < 1_000_000 else 50_000
    return max(MIN_SALARY, int(round(amount / step) * step))


def grade_position(value: float, kind: str) -> float:
    """
    Where a rating sits on the grade curve, as a fractional index into
    GRADES: 0 is the bottom of A+, 1 the bottom of A, ... 12 is F. Ratings
    above the A+ cutoff go below 0, a grade's width per 3 points.
    """
    cuts = OVERALL_CUTOFFS[kind]
    if value >= cuts[0]:
        return -(value - cuts[0]) / 3.0
    for i in range(1, len(cuts)):
        hi, lo = cuts[i - 1], cuts[i]
        if value >= lo:
            return i - (value - lo) / (hi - lo)
    return float(len(GRADES) - 1)


def prime_salary(value: float, kind: str) -> float:
    """What a prime-age player with this rating is worth a season, sliding
    smoothly (geometrically) between the grade steps in GRADE_SALARY."""
    pos = grade_position(value, kind)
    pays = [GRADE_SALARY[g] for g in GRADES]
    if pos <= 0:
        # Past A+: keep climbing at the A to A+ rate, up to the max.
        rate = pays[0] / pays[1]
        return min(MAX_SALARY, pays[0] * rate ** (-pos))
    i = min(int(pos), len(pays) - 2)
    frac = pos - i
    return pays[i] * (pays[i + 1] / pays[i]) ** frac


def age_factor(age: int) -> float:
    """Teams pay less for the years a player is likely to decline."""
    if age >= 37:
        return 0.55
    if age >= 35:
        return 0.7
    if age >= 33:
        return 0.85
    return 1.0


def standard_years(age: int, value: float, kind: str, rng: random.Random) -> int:
    """How many seasons a standard deal runs: long for young stars, short
    for old or fringe players."""
    pos = grade_position(value, kind)
    if pos >= GRADES.index("C-"):
        lo, hi = 1, 2  # fringe players go year to year
    elif age <= 30:
        lo, hi = 2, 5
    elif age <= 33:
        lo, hi = 1, 3
    else:
        lo, hi = 1, 2
    if pos <= GRADES.index("A-") and age <= 30:
        lo, hi = max(lo, 4), 7  # stars lock in for longer
    return rng.randint(lo, hi)


def standard_deal(age: int, value: float, kind: str, rng: random.Random) -> Deal:
    salary = prime_salary(value, kind) * age_factor(age)
    salary *= 1 + rng.uniform(-SALARY_NOISE, SALARY_NOISE)
    return Deal(round_salary(salary), standard_years(age, value, kind, rng), "standard")


def rookie_salary(pick_number: int) -> int:
    """A rookie deal's salary for the nth pick of the draft (1 = first)."""
    bonus = TOP_PICK_BONUS * math.exp(-(max(1, pick_number) - 1) / BONUS_DECAY_PICKS)
    return round_salary(MIN_SALARY + bonus / ROOKIE_YEARS)


def rookie_deal(pick_number: int) -> Deal:
    return Deal(rookie_salary(pick_number), ROOKIE_YEARS, "rookie")


def years_already_served(years: int, rng: random.Random) -> int:
    """For a league's starting rosters: how far into his deal a player
    already is, so the deals don't all run out together."""
    return rng.randint(0, years - 1)


def format_salary(amount: int | None) -> str:
    """$780K, $4.5M, $32M."""
    if amount is None:
        return "—"
    if amount >= 1_000_000:
        text = f"{amount / 1_000_000:.1f}".removesuffix(".0")
        return f"${text}M"
    return f"${round(amount / 1000)}K"
