# src/player/talent_caps.py
"""
Talent Cap Generation

Each player is born with a per-skill talent cap — the maximum value that
skill can reach over their career through normal development. Two players
generated with identical base skills can have genuinely different ceilings,
making scouting non-trivial and development unpredictable.

Design:
- Cap = base + growth, where growth ~ Normal(expected_growth(base), sigma)
- expected_growth() is a tent function: most room in the middle (40-60),
  less room at the extremes (already elite, or floor-level with no talent)
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


def expected_growth(base: int) -> float:
    """
    Central tendency for how much a skill grows from base to peak.

    Tent-shaped: most room to grow in the 40-55 range (average player
    with real development potential). Less room at the top (already elite)
    and very little at the bottom (floor-level, no latent talent).

    Args:
        base: Starting skill value (1-100)

    Returns:
        Expected growth in skill points over career
    """
    if base < 25:
        return 4.0  # near floor — almost no ceiling, skill is essentially frozen
    if base < 40:
        return 12.0  # below average — modest ceiling
    if base < 55:
        return 20.0  # average — most development potential
    if base < 70:
        return 15.0  # above average — less room to grow
    return 8.0  # already elite — near their ceiling at generation


def generate_talent_caps(
    skills: dict[str, int],
    rng: random.Random,
) -> dict[str, int]:
    """
    Generate per-player talent caps for all skills.

    Each cap is drawn from a normal distribution centered at
    base + expected_growth(base), with skill-specific sigma.
    Growth is floored at 0 so the cap is always >= base.

    Args:
        skills: The player's generated base skills (full-name keys)
        rng:    Seeded RNG for reproducibility

    Returns:
        Dictionary mapping skill name → talent cap (1-100)

    Example:
        Two players with stamina=50:
          player A: cap = 50 + gauss(20, 10) = 50 + 23 = 73
          player B: cap = 50 + gauss(20, 10) = 50 + 7  = 57
    """
    caps = {}
    for skill, base in skills.items():
        sigma = TALENT_SIGMA.get(skill, _DEFAULT_SIGMA)
        growth = rng.gauss(expected_growth(base), sigma)
        growth = max(0.0, growth)  # never below base
        cap = base + int(round(growth))
        caps[skill] = min(cap, 100)  # absolute ceiling
    return caps
