# src/player/talent_caps.py
"""
Talent Cap Generation

Each player is born with a per-skill talent cap — the maximum value that
skill can reach over their career through normal development. Two players
generated with identical base skills can have genuinely different ceilings,
making scouting non-trivial and development unpredictable.

Design:
- Cap = base + growth, where growth ~ Normal(expected_growth(base, skill), sigma)
- expected_growth() starts from the aging curve's planned_growth() for the
  skill, so the cap leaves room for the whole curve and the curve, not the
  cap, decides when a player peaks. Floor-level skills (no latent talent)
  get a fraction of it, and elite skills get somewhat less room
- sigma varies by skill: physical tools observable with radar/timing are
  more predictable; mental/craft skills are harder to project
- Cap is soft: the aging curve dampens growth as value approaches cap,
  but noise can occasionally push slightly past it
- Cap is stored at creation and never changes (injuries/bad habits not
  modeled here — that's a future system)
- Cap floor = base value (a player never develops below their starting point
  on average; equal cap means the skill is essentially frozen)
"""

import random

from src.player.player_skill_aging import SKILL_CURVES, planned_growth

# ── Skill sigma: how unpredictable is the ceiling for this skill? ──
# Lower = more predictable (scouts can evaluate it early)
# Higher = harder to project (fog of war matters more here)
TALENT_SIGMA: dict[str, float] = {
    # Physical tools — observable with instruments, but development varies
    "speed": 8.0,  # sprint timing is exact; ceiling varies a lot
    "arm": 6.0,  # radar gun; most predictable physical tool
    "power": 9.0,  # exit velo hints at ceiling but varies most
    "durability": 12.0,  # little harder to detect
    # Craft / mental — hardest to project
    "contact": 12.0,  # genuinely hard to scout in minors
    "eye": 11.0,  # walk rate needs huge sample to stabilize
    "clutch": 14.0,  # essentially unknowable until high-leverage ABs
    "base_running": 9.0,
    # Pitcher physical
    "strikes": 7.0,  # spin rate/velo visible; development still varies
    "stamina": 10.0,  # usage patterns confound projection
    "recovery": 11.0,  # nearly invisible until years of data
    "ground_balls": 8.0,
    "accuracy": 10.0,
    # Technique
    "catching": 9.0,
    "infield": 9.0,
    "outfield": 8.0,
    "bunting": 6.0,  # pure technique; fairly predictable
}

# Fallback sigma for any skill not listed
_DEFAULT_SIGMA = 9.0


# Planned growth for any skill without an aging curve
_DEFAULT_GROWTH = 15.0

# Below this base a skill is floor-level (e.g. a pitcher's hitting) and
# gets only FLOOR_ROOM of the planned growth.
FLOOR_BASE = 25
FLOOR_ROOM = 0.3

# From ELITE_BASE up, room shrinks linearly to ELITE_MIN_ROOM at ELITE_FULL_BASE.
ELITE_BASE = 70
ELITE_FULL_BASE = 90
ELITE_MIN_ROOM = 0.5


def growth_room(base: int) -> float:
    """
    Share of the curve's planned growth a skill at *base* has room for.

    1.0 across the normal range, a small share for floor-level skills, and
    tapering for already-elite skills (but never below half, so a top
    prospect still develops).
    """
    if base < FLOOR_BASE:
        return FLOOR_ROOM
    if base < ELITE_BASE:
        return 1.0
    taper = (base - ELITE_BASE) / (ELITE_FULL_BASE - ELITE_BASE)
    return max(ELITE_MIN_ROOM, 1.0 - taper * (1.0 - ELITE_MIN_ROOM))


def expected_growth(base: int, skill: str) -> float:
    """
    Central tendency for how much a skill grows from base to peak.

    Args:
        base:  Starting skill value (1-100)
        skill: Full skill name, e.g. "contact"

    Returns:
        Expected growth in skill points over career
    """
    growth = planned_growth(skill) if skill in SKILL_CURVES else _DEFAULT_GROWTH
    return growth * growth_room(base)


def generate_talent_caps(
    skills: dict[str, int],
    rng: random.Random,
) -> dict[str, int]:
    """
    Generate per-player talent caps for all skills.

    Each cap is drawn from a normal distribution centered at
    base + expected_growth(base, skill), with skill-specific sigma.
    Growth is floored at 0 so the cap is always >= base.

    Args:
        skills: The player's generated base skills (full-name keys)
        rng:    Seeded RNG for reproducibility

    Returns:
        Dictionary mapping skill name → talent cap (1-100)

    Example:
        Two players with stamina=50 (planned growth 11.6):
          player A: cap = 50 + gauss(11.6, 10) = 50 + 19 = 69
          player B: cap = 50 + gauss(11.6, 10) = 50 + 4  = 54
    """
    caps = {}
    for skill, base in skills.items():
        sigma = TALENT_SIGMA.get(skill, _DEFAULT_SIGMA)
        growth = rng.gauss(expected_growth(base, skill), sigma)
        growth = max(0.0, growth)  # never below base
        cap = base + int(round(growth))
        caps[skill] = min(cap, 100)  # absolute ceiling
    return caps
