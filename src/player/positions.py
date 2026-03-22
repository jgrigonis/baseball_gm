# src/player/positions.py
"""
Baseball position definitions and templates.

This module defines:
- Position codes and names
- Position-specific handedness probabilities
- Position-specific skill templates (means for random generation)
- Default skill values

Position codes are 1-4 character abbreviations (e.g., "sp", "ss", "cf").
Skills are referenced by their full names from skill_map.py.
All skill values range from 1-100, with 50 being league average.
"""

__author__ = "josh"

from types import MappingProxyType
from typing import Literal
from typing import TypedDict

# Import skill definitions for consistency
# Note: Actual skills should be validated against SKILL_MAP from skill_map.py


class PositionTemplate(TypedDict):
    throws_left: float
    switch_hitter: float
    bats_left: float


# ---------- Position Definitions ----------

# Position affinities used for skill generation
# These determine skill distributions when creating players
AFFINITY_POSITIONS: list[str] = [
    "sp",  # starting pitcher
    "rp",  # relief pitcher
    "c",  # catcher
    "1b",  # first baseman
    "2b",  # second baseman
    "ss",  # shortstop
    "3b",  # third baseman
    "lf",  # left fielder
    "cf",  # center fielder
    "rf",  # right fielder
    "if",  # utility infielder
    "of",  # outfielder
    "dh",  # designated hitter
]

# In-game positions (what appears in box scores/lineups)
# More generic - "p" for any pitcher during gameplay
IN_GAME_POSITIONS: list[str] = [
    "p",  # pitcher (generic, in-game)
    "c",  # catcher
    "1b",  # first baseman
    "2b",  # second baseman
    "ss",  # shortstop
    "3b",  # third baseman
    "lf",  # left fielder
    "cf",  # center fielder
    "rf",  # right fielder
    "dh",  # designated hitter
]

# All valid position codes (affinity + in-game combined)
ALL_POSITIONS: set[str] = set(AFFINITY_POSITIONS + IN_GAME_POSITIONS)

# Legacy: backward compatibility
POSITIONS = AFFINITY_POSITIONS

# Full position names
POSITION_NAME: MappingProxyType[str, str] = MappingProxyType(
    {
        # Affinity positions
        "sp": "starting pitcher",
        "rp": "relief pitcher",
        "c": "catcher",
        "1b": "first baseman",
        "2b": "second baseman",
        "ss": "shortstop",
        "3b": "third baseman",
        "lf": "left fielder",
        "cf": "center fielder",
        "rf": "right fielder",
        "if": "utility infielder",
        "of": "outfielder",
        "dh": "designated hitter",
        # In-game positions
        "p": "pitcher",  # Generic pitcher for in-game use
    }
)

# Reverse mapping: name -> code
POSITION_ABBR: dict[str, str] = {v: k for k, v in POSITION_NAME.items()}

# Position categories
PITCHER_POSITIONS: list[str] = ["sp", "rp", "p"]
INFIELD_POSITIONS: list[str] = ["c", "1b", "2b", "ss", "3b", "if"]
OUTFIELD_POSITIONS: list[str] = ["lf", "cf", "rf", "of"]
DEFENSIVE_POSITIONS: list[str] = INFIELD_POSITIONS + OUTFIELD_POSITIONS
UTILITY_POSITIONS: list[str] = ["if", "of", "dh"]

# Type alias for valid positions
AffinityPosition = Literal[
    "sp", "rp", "c", "1b", "2b", "ss", "3b", "lf", "cf", "rf", "if", "of", "dh"
]

InGamePosition = Literal["p", "c", "1b", "2b", "ss", "3b", "lf", "cf", "rf", "dh"]

Position = Literal[
    "sp", "rp", "p", "c", "1b", "2b", "ss", "3b", "lf", "cf", "rf", "if", "of", "dh"
]

# ---------- Handedness Probabilities ----------

POSITION_TEMPLATES: MappingProxyType[str, dict[str, float]] = MappingProxyType(
    {
        "sp": {
            # 25% of starting pitchers are left handed (realistic MLB ratio)
            "throws_left": 0.25,
            "switch_hitter": 0.01,  # Pitchers rarely switch hit
            "bats_left": 0.01,  # Most pitchers bat same side they throw
        },
        "rp": {
            # 35% of relief pitchers are left handed (LOOGYs, specialists)
            "throws_left": 0.35,
            "switch_hitter": 0.01,
            "bats_left": 0.01,
        },
        "c": {
            # Almost impossible to be a left-handed catcher (throwing to 2nd/3rd)
            "throws_left": 0.001,
            "switch_hitter": 0.16,
            "bats_left": 0.12,
        },
        "1b": {
            # Left-handed 1B are common (easier to field and throw to other bases)
            "throws_left": 0.33,
            "switch_hitter": 0.12,
            "bats_left": 0.12,
        },
        "ss": {
            # Almost no left-handed SS (difficult to turn double plays)
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.05,
        },
        "2b": {
            # Almost no left-handed 2B (difficult positioning on double plays)
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.15,
        },
        "3b": {
            # Almost no left-handed 3B (throwing across diamond)
            "throws_left": 0.001,
            "switch_hitter": 0.15,
            "bats_left": 0.05,
        },
        "lf": {
            "throws_left": 0.25,
            "switch_hitter": 0.10,
            "bats_left": 0.15,
        },
        "cf": {
            # More left-handed CF (premium athletes)
            "throws_left": 0.33,
            "switch_hitter": 0.16,
            "bats_left": 0.15,
        },
        "rf": {
            "throws_left": 0.25,
            "switch_hitter": 0.10,
            "bats_left": 0.15,
        },
        "if": {
            # Almost no left-handed utility infielders
            "throws_left": 0.001,
            "switch_hitter": 0.25,
            "bats_left": 0.15,
        },
        "of": {
            "throws_left": 0.30,
            "switch_hitter": 0.20,
            "bats_left": 0.15,
        },
        "dh": {
            "throws_left": 0.33,
            "switch_hitter": 0.15,
            "bats_left": 0.20,
        },
    }
)

# ---------- Position Skill Templates ----------

# Mean skill values for random player generation by position
# Any skill not listed defaults to 50 (league average)
# Values represent typical skill levels: 50=average, 70=good, 30=poor

SKILL_TEMPLATE: MappingProxyType[str, dict[str, int]] = MappingProxyType(
    {
        "sp": {
            "accuracy": 55,  # Good control for starters
            "stamina": 55,  # High stamina to pitch deep into games
            "recovery": 60,  # Good recovery between starts
            "power": 20,  # Pitchers are poor hitters
            "eye": 30,
            "contact": 30,
            "base_running": 40,
            "catching": 20,  # Not a defensive position
            "infield": 40,
            "outfield": 40,
            "arm": 60,  # Strong arms
        },
        "rp": {
            "accuracy": 55,
            "recovery": 55,  # Need to bounce back quickly
            # stamina defaults to 50 (relievers need less)
            "power": 20,
            "eye": 30,
            "contact": 30,
            "base_running": 40,
            "catching": 20,
            "infield": 40,
            "outfield": 40,
            "arm": 60,
        },
        "c": {
            # Pitching skills very low
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            # Defensive skills high
            "base_running": 40,  # Catchers are typically slower
            "catching": 70,  # Elite catching skill
            "infield": 40,
            "outfield": 40,
            "arm": 60,  # Strong arms to throw out runners
        },
        "1b": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 30,  # 1B are typically slower
            "power": 60,  # Expected to hit for power
            "base_running": 40,
            "outfield": 40,
            # catching and infield default to 50
        },
        "ss": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 60,  # SS are typically fast
            "power": 35,  # Less power, more contact hitters
            "infield": 70,  # Elite infield defense
            # outfield defaults to 50
        },
        "2b": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 60,
            "power": 35,
            "infield": 70,
        },
        "3b": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "infield": 60,  # Good infield defense
            # power defaults to 50
        },
        "lf": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 60,
            "power": 60,  # Corner OF hit for power
            "catching": 40,
            "infield": 40,
            "outfield": 60,
        },
        "cf": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 65,  # CF are fastest OF
            "catching": 40,
            "infield": 40,
            "outfield": 65,  # Elite OF defense
            "arm": 60,
        },
        "rf": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 60,
            "power": 60,
            "catching": 40,
            "infield": 40,
            "outfield": 60,
            "arm": 60,  # RF need strong arms
        },
        "if": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "infield": 60,
            "power": 35,
        },
        "of": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "speed": 55,
            "catching": 40,
            "infield": 40,
            "outfield": 60,
        },
        "dh": {
            "accuracy": 10,
            "stamina": 10,
            "recovery": 10,
            "ground_balls": 10,
            "strikes": 10,
            "power": 65,  # DH are power hitters
            "catching": 40,
            "infield": 40,
            "outfield": 40,
            "arm": 40,
        },
    }
)

# ---------- Default Skill Values ----------

# Base skill values when not specified in position template
# 50 represents league average for all skills
# Skills range from 1 (worst) to 100 (best)

SKILLS: MappingProxyType[str, int] = MappingProxyType(
    {
        # Pitching
        "accuracy": 50,  # Control, ability to hit spots
        "stamina": 50,  # Pitch count capacity (50 = ~100 pitches)
        "recovery": 50,  # Days to recover stamina (50 = 5 days)
        "ground_balls": 50,  # Ground ball tendency
        "strikes": 50,  # Swing-and-miss ability (stuff)
        # General
        "clutch": 50,  # Performance in high-pressure situations
        "speed": 50,  # Running speed
        "durability": 50,  # player durability
        # Hitting
        "power": 50,  # Home run power
        "eye": 50,  # Plate discipline, walk rate
        "contact": 50,  # Ability to make contact
        "base_running": 50,  # Base running instincts
        "bunting": 50,  # Bunting ability
        # Defense
        "catching": 50,  # Catcher-specific skills
        "infield": 50,  # Infield defense
        "outfield": 50,  # Outfield defense
        "arm": 50,  # Throwing arm strength
    }
)

# ---------- Helper Functions ----------


def is_valid_position(position: str) -> bool:
    """
    Check if position code is valid (affinity or in-game).

    Args:
        position: Position code to check

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_position("ss")
        True
        >>> is_valid_position("p")
        True
        >>> is_valid_position("qb")
        False
    """
    return position in ALL_POSITIONS


def is_valid_affinity_position(position: str) -> bool:
    """
    Check if position code is a valid affinity position.

    Affinity positions are used for skill generation and player creation.

    Args:
        position: Position code to check

    Returns:
        True if valid affinity position, False otherwise

    Example:
        >>> is_valid_affinity_position("sp")
        True
        >>> is_valid_affinity_position("p")
        False
    """
    return position in AFFINITY_POSITIONS


def is_valid_in_game_position(position: str) -> bool:
    """
    Check if position code is a valid in-game position.

    In-game positions are used during actual gameplay and box scores.

    Args:
        position: Position code to check

    Returns:
        True if valid in-game position, False otherwise

    Example:
        >>> is_valid_in_game_position("p")
        True
        >>> is_valid_in_game_position("sp")
        False
    """
    return position in IN_GAME_POSITIONS


def get_position_name(position: str) -> str:
    """
    Get full position name from code.

    Args:
        position: Position code (e.g., "ss")

    Returns:
        Full position name (e.g., "shortstop")

    Raises:
        ValueError: If position is not valid

    Example:
        >>> get_position_name("ss")
        'shortstop'
    """
    if position not in POSITION_NAME:
        raise ValueError(
            f"Unknown position: '{position}'. "
            f"Valid positions: {', '.join(POSITIONS)}"
        )
    return POSITION_NAME[position]


def get_position_code(position_name: str) -> str:
    """
    Get position code from full name.

    Args:
        position_name: Full position name (e.g., "shortstop")

    Returns:
        Position code (e.g., "ss")

    Raises:
        ValueError: If position name is not valid

    Example:
        >>> get_position_code("shortstop")
        'ss'
    """
    if position_name not in POSITION_ABBR:
        raise ValueError(
            f"Unknown position name: '{position_name}'. "
            f"Valid names: {', '.join(sorted(POSITION_ABBR.keys()))}"
        )
    return POSITION_ABBR[position_name]


def is_pitcher(position: str) -> bool:
    """
    Check if position is a pitcher.

    Args:
        position: Position code

    Returns:
        True if pitcher, False otherwise

    Example:
        >>> is_pitcher("sp")
        True
        >>> is_pitcher("ss")
        False
    """
    return position in PITCHER_POSITIONS


def is_infielder(position: str) -> bool:
    """
    Check if position is an infielder (including catcher).

    Args:
        position: Position code

    Returns:
        True if infielder, False otherwise
    """
    return position in INFIELD_POSITIONS


def is_outfielder(position: str) -> bool:
    """
    Check if position is an outfielder.

    Args:
        position: Position code

    Returns:
        True if outfielder, False otherwise
    """
    return position in OUTFIELD_POSITIONS


def get_position_category(position: str) -> str:
    """
    Get the category of a position.

    Works with both affinity and in-game positions.

    Args:
        position: Position code

    Returns:
        Category: "pitcher", "infield", "outfield", or "utility"

    Raises:
        ValueError: If position is not valid

    Example:
        >>> get_position_category("ss")
        'infield'
        >>> get_position_category("sp")
        'pitcher'
        >>> get_position_category("p")
        'pitcher'
    """
    if position not in ALL_POSITIONS:
        raise ValueError(f"Unknown position: '{position}'")

    if position in PITCHER_POSITIONS or position == "p":
        return "pitcher"
    elif position in INFIELD_POSITIONS:
        return "infield"
    elif position in OUTFIELD_POSITIONS:
        return "outfield"
    else:
        return "utility"


def get_complete_skills(position: str) -> dict[str, int]:
    """
    Get all skills for a position with defaults applied.

    Only works with affinity positions (sp, rp, etc.).
    Use this for player generation, not in-game positions.

    Args:
        position: Affinity position code

    Returns:
        Dictionary of skill_name -> value with position template applied

    Raises:
        ValueError: If position is not a valid affinity position

    Example:
        >>> skills = get_complete_skills("ss")
        >>> skills["infield"]
        70
        >>> skills["bunting"]  # Not in template, uses default
        50
    """
    if position not in AFFINITY_POSITIONS:
        raise ValueError(
            f"Position '{position}' is not a valid affinity position. "
            f"Use one of: {', '.join(AFFINITY_POSITIONS)}"
        )

    # Start with defaults
    complete_skills = dict(SKILLS)

    # Apply position-specific overrides
    position_overrides = SKILL_TEMPLATE.get(position, {})
    complete_skills.update(position_overrides)

    return complete_skills


def get_handedness_probabilities(position: str) -> dict[str, float]:
    """
    Get handedness probabilities for a position.

    Args:
        position: Position code

    Returns:
        Dictionary with throws_left, switch_hitter, bats_left probabilities

    Raises:
        ValueError: If position is not valid

    Example:
        >>> probs = get_handedness_probabilities("c")
        >>> probs["throws_left"]
        0.001
    """
    if position not in POSITION_TEMPLATES:
        raise ValueError(f"Unknown position: '{position}'")

    return dict(POSITION_TEMPLATES[position])


def format_position(position: str) -> str:
    """
    Format position for display.

    Args:
        position: Position code

    Returns:
        Formatted string (e.g., "Shortstop (SS)")

    Example:
        >>> format_position("ss")
        'Shortstop (SS)'
    """
    name = get_position_name(position)
    return f"{name.title()} ({position.upper()})"


# ---------- Validation Sets ----------

ALL_POSITIONS_SET: set[str] = ALL_POSITIONS  # Already a set
ALL_POSITION_NAMES: set[str] = set(POSITION_NAME.values())
AFFINITY_POSITIONS_SET: set[str] = set(AFFINITY_POSITIONS)
IN_GAME_POSITIONS_SET: set[str] = set(IN_GAME_POSITIONS)
