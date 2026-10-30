# src/league/front_office.py
"""
How an AI GM's team state and persona steer its roster decisions
(plans/ai-gm-strategy.md, section 7, "What reads it"): the draft, who makes
the 26-man and 40-man, playing time, protecting young arms and offseason
trimming. Trades read them in src/league/trades/ai_evaluator.py.

The common thread is a youth tilt, from -1 (play the veterans) to 1 (play
the kids): mostly the team state (a rebuilding team plays its prospects, an
all-in team its veterans), moved by the persona's youth dial. A player gets
age_points(age, tilt) rating points on top of his rating wherever an AI team
ranks its players, at most MAX_AGE_POINTS either way, so a tilt decides
between players who are close and never puts a scrub ahead of a regular.

People's teams aren't touched: they pick their own roster and lineup.
"""

from __future__ import annotations

from dataclasses import replace

from src.league.offseason.draft_strategy import (
    CHIPS,
    HIGH,
    LOW,
    MED,
    DraftStrategy,
)
from src.league.personas import Leanings
from src.team.manager_profile import ManagerProfile

# How each state leans, -1 (veterans) to 1 (kids).
STATE_YOUTH = {
    "all-in": -0.6,
    "contending": -0.2,
    "retooling": 0.0,
    "ramping-up": 0.5,
    "rebuilding": 0.8,
    "aging-out": 0.4,
}
# The youth dial at either end moves the tilt by this much.
PERSONA_YOUTH = 0.5

# A player PRIME_AGE has no age points; each year younger (or older) is
# POINTS_PER_YEAR at full tilt, up to MAX_AGE_POINTS.
PRIME_AGE = 27
POINTS_PER_YEAR = 0.6
MAX_AGE_POINTS = 3.0

# The draft's age slider (-1 upside … 1 ready sooner) by state; the persona's
# youth and risk dials move it toward upside.
STATE_DRAFT_AGE = {
    "all-in": 0.8,
    "contending": 0.3,
    "retooling": 0.0,
    "ramping-up": -0.5,
    "rebuilding": -0.7,
    "aging-out": -0.5,
}
DRAFT_YOUTH = 0.3
DRAFT_RISK = 0.2
# Contenders and rebuilders take the best player available, so their need
# chips drop a level; a retooling team drafts for need, so its go up one.
BEST_AVAILABLE = {"contending", "rebuilding", "all-in"}
FOR_NEED = {"retooling"}
# A bat-first GM asks for offense in the draft.
BAT_FIRST = 70

# States whose AI teams protect young arms: they skip a tired starter and
# keep a pitch count (no letting him work).
PROTECT_ARMS = {"rebuilding", "ramping-up"}

# The defense weight in the lineup builder at the glove-first and bat-first
# ends of the offense-vs-defense dial.
DEFENSE_RANGE = 0.5


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def youth_tilt(state: str | None, lean: Leanings) -> float:
    """-1 (veterans) to 1 (kids)."""
    base = STATE_YOUTH.get(state or "", 0.0)
    return _clamp(base + PERSONA_YOUTH * (lean.youth - 50) / 50)


def age_points(age: int, tilt: float) -> float:
    """Rating points a player of this age gets from a team with this tilt."""
    if not tilt:
        return 0.0
    points = tilt * POINTS_PER_YEAR * (PRIME_AGE - age)
    return max(-MAX_AGE_POINTS, min(MAX_AGE_POINTS, points))


def draft_strategy(
    needs: dict[str, int], state: str | None, lean: Leanings
) -> DraftStrategy:
    """An AI team's draft strategy: its roster's needs, weighed by its state
    (best available or need) and persona, and an age slider from both."""
    shift = -1 if state in BEST_AVAILABLE else 1 if state in FOR_NEED else 0
    chips = {
        k: max(LOW, min(HIGH, level + shift))
        for k, level in needs.items()
        if k in CHIPS
    }
    if lean.offense_defense >= BAT_FIRST:
        chips["offense"] = max(chips.get("offense", LOW), MED)
    chips = {k: v for k, v in chips.items() if v > LOW}
    age = (
        STATE_DRAFT_AGE.get(state or "", 0.0)
        - DRAFT_YOUTH * (lean.youth - 50) / 50
        - DRAFT_RISK * (lean.risk - 50) / 50
    )
    return DraftStrategy(chips=chips, age_pref=round(_clamp(age), 3))


def defense_weight(lean: Leanings) -> float:
    """Multiplies how much a glove counts in the lineup builder: 1.5 for the
    most glove-first GM, 0.5 for the most bat-first, 1 in the middle."""
    return 1 + DEFENSE_RANGE * (50 - lean.offense_defense) / 50


def protect_arms(profile: ManagerProfile) -> ManagerProfile:
    """A shorter leash: tired starters skip a turn, and a starter who'd be
    left in to work goes by the pitch count instead."""
    usage = (
        "pitch-count-strict"
        if profile.starter_usage == "let-them-work"
        else profile.starter_usage
    )
    return replace(profile, tired_starters="protect", starter_usage=usage)
