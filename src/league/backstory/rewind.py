# src/league/backstory/rewind.py
"""
A player's ratings at younger ages, for the seasons before the league
started.

Players are made at 17 and aged forward to their roster age with the curves
in src/player/player_skill_aging.py. Rewinding runs those same curves
backwards: each year back takes off the change the curve expects that year
(slowed near the player's talent cap, as aging is), plus a little noise so
careers don't all have the same shape. A change to the aging curves carries
over here with nothing to update.
"""

from __future__ import annotations

import random

from src.player.player_skill_aging import SKILL_CURVES, _cap_dampen, _phase_index
from src.player.player_skills import SKILL_MAX, SKILL_MIN

# Spread (one standard deviation, in skill points) added to each skill for
# each year rewound.
NOISE_SCALE_BACK = 0.5


def _expected_change(skill: str, age: int, value: float, cap: int | None) -> float:
    """The change the aging curve expects from `age` to `age + 1` for a
    player who ends the year at `value`."""
    breaks, rates = SKILL_CURVES[skill]
    rate = rates[_phase_index(age, breaks)]
    # Dampen as aging does, judged from where the player started the year.
    return _cap_dampen(rate, value - rate, cap)


def rewind(
    skills: dict[str, float],
    age: int,
    years: int,
    caps: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> list[dict[str, float]]:
    """The player's skills 1, 2, ... `years` years ago: element k - 1 is k
    years back, at age `age - k`. Values stay floats in the skill range;
    skills without an aging curve (none today) carry over unchanged."""
    rng = rng or random.Random()
    out = []
    current = dict(skills)
    for k in range(1, years + 1):
        prev_age = age - k
        prev = {}
        for skill, value in current.items():
            if skill not in SKILL_CURVES:
                prev[skill] = value
                continue
            cap = caps.get(skill) if caps else None
            v = value - _expected_change(skill, prev_age, value, cap)
            v += rng.gauss(0, NOISE_SCALE_BACK)
            prev[skill] = min(float(SKILL_MAX), max(float(SKILL_MIN), v))
        out.append(prev)
        current = prev
    return out
