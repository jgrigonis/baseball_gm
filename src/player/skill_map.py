# src/player/skill_map.py
"""
Player skill definitions and mappings.

Skills are organized into four categories:
- Hitting: Offensive skills for batters (power, eye, contact, base running, bunting)
- Defense: Fielding and positioning skills (catching, infield, outfield, arm)
- Pitching: Skills specific to pitchers (accuracy, stamina, recovery, ground balls, strikes)
- General: Skills that apply to all players (clutch, speed)

Each skill has a two-letter abbreviation used for compact storage and display.
"""

__author__ = "josh"

from typing import Literal

# Core skill mapping: abbreviation -> full name
SKILL_MAP: dict[str, str] = {
    # Hitting
    "PO": "power",
    "EY": "eye",
    "CT": "contact",
    "BR": "base_running",
    "BU": "bunting",
    # Defense
    "CA": "catching",
    "IF": "infield",
    "OF": "outfield",
    "AR": "arm",
    # Pitching
    "AC": "accuracy",
    "ST": "stamina",
    "RE": "recovery",
    "GB": "ground_balls",
    "KK": "strikes",
    # General
    "CL": "clutch",
    "SP": "speed",
}

# Reverse mapping: full name -> abbreviation
SKILL_ABBREVIATIONS: dict[str, str] = {v: k for k, v in SKILL_MAP.items()}

# Skill categories
SKILL_CATEGORIES: dict[str, list[str]] = {
    "hitting": ["PO", "EY", "CT", "BR", "BU"],
    "defense": ["CA", "IF", "OF", "AR"],
    "pitching": ["AC", "ST", "RE", "GB", "KK"],
    "general": ["CL", "SP"],
}

# Skill value constraints
SKILL_MIN = 1
SKILL_MAX = 100

# Type alias for valid skill categories
SkillCategory = Literal["hitting", "defense", "pitching", "general"]

# Type alias for valid skill abbreviations
SkillAbbr = Literal[
    "PO",
    "EY",
    "CT",
    "BR",
    "BU",  # Hitting
    "CA",
    "IF",
    "OF",
    "AR",  # Defense
    "AC",
    "ST",
    "RE",
    "GB",
    "KK",  # Pitching
    "CL",
    "SP",  # General
]


# ---------- Helper Functions ----------


def get_skill_name(abbreviation: str) -> str:
    """
    Get the full skill name from its abbreviation.

    Args:
        abbreviation: Two-letter skill abbreviation (e.g., "PO")

    Returns:
        Full skill name (e.g., "power")

    Raises:
        ValueError: If abbreviation is not a valid skill

    Example:
        >>> get_skill_name("PO")
        'power'
    """
    if abbreviation not in SKILL_MAP:
        raise ValueError(
            f"Unknown skill abbreviation: '{abbreviation}'. "
            f"Valid abbreviations: {', '.join(sorted(SKILL_MAP.keys()))}"
        )
    return SKILL_MAP[abbreviation]


def get_skill_abbr(skill_name: str) -> str:
    """
    Get the abbreviation from the full skill name.

    Args:
        skill_name: Full skill name (e.g., "power")

    Returns:
        Two-letter abbreviation (e.g., "PO")

    Raises:
        ValueError: If skill_name is not valid

    Example:
        >>> get_skill_abbr("power")
        'PO'
    """
    abbr = SKILL_ABBREVIATIONS.get(skill_name)
    if abbr is None:
        raise ValueError(
            f"Unknown skill name: '{skill_name}'. "
            f"Valid names: {', '.join(sorted(SKILL_ABBREVIATIONS.keys()))}"
        )
    return abbr


def is_valid_skill(abbreviation: str) -> bool:
    """
    Check if an abbreviation is a valid skill.

    Args:
        abbreviation: Two-letter code to check

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_skill("PO")
        True
        >>> is_valid_skill("XX")
        False
    """
    return abbreviation in SKILL_MAP


def is_valid_skill_value(value: int) -> bool:
    """
    Check if a skill value is within valid range.

    Args:
        value: Skill value to check

    Returns:
        True if value is between SKILL_MIN and SKILL_MAX (inclusive)

    Example:
        >>> is_valid_skill_value(50)
        True
        >>> is_valid_skill_value(0)
        False
        >>> is_valid_skill_value(101)
        False
    """
    return SKILL_MIN <= value <= SKILL_MAX


def validate_skill_value(value: int, skill_abbr: str | None = None) -> None:
    """
    Validate that a skill value is within the allowed range.

    Args:
        value: The skill value to validate
        skill_abbr: Optional skill abbreviation for better error messages

    Raises:
        ValueError: If value is outside valid range

    Example:
        >>> validate_skill_value(50)
        >>> validate_skill_value(101, "PO")
        ValueError: Skill value for 'PO' must be between 1 and 100, got 101
    """
    if not isinstance(value, int):
        skill_msg = f" for '{skill_abbr}'" if skill_abbr else ""
        raise TypeError(
            f"Skill value{skill_msg} must be an integer, got {type(value).__name__}"
        )

    if not is_valid_skill_value(value):
        skill_msg = f" for '{skill_abbr}'" if skill_abbr else ""
        raise ValueError(
            f"Skill value{skill_msg} must be between {SKILL_MIN} and {SKILL_MAX}, got {value}"
        )


def get_skills_by_category(category: str) -> list[str]:
    """
    Get all skill abbreviations in a category.

    Args:
        category: Category name ("hitting", "defense", "pitching", "general")

    Returns:
        List of skill abbreviations in that category

    Raises:
        ValueError: If category is not valid

    Example:
        >>> get_skills_by_category("hitting")
        ['CL', 'PO', 'EY', 'CT', 'BR', 'BU']
    """
    if category not in SKILL_CATEGORIES:
        raise ValueError(
            f"Unknown category: '{category}'. "
            f"Valid categories: {', '.join(SKILL_CATEGORIES.keys())}"
        )
    return list(SKILL_CATEGORIES[category])


def get_skill_category(abbreviation: str) -> str:
    """
    Get the category of a skill.

    Args:
        abbreviation: Two-letter skill abbreviation

    Returns:
        Category name ("hitting", "defense", "pitching", or "general")

    Raises:
        ValueError: If abbreviation is not a valid skill

    Example:
        >>> get_skill_category("PO")
        'hitting'
        >>> get_skill_category("AC")
        'pitching'
    """
    for category, skills in SKILL_CATEGORIES.items():
        if abbreviation in skills:
            return category

    raise ValueError(
        f"Unknown skill abbreviation: '{abbreviation}'. "
        f"Valid abbreviations: {', '.join(sorted(SKILL_MAP.keys()))}"
    )


def get_all_skills() -> list[str]:
    """
    Get all skill abbreviations.

    Returns:
        List of all skill abbreviations in alphabetical order

    Example:
        >>> skills = get_all_skills()
        >>> "PO" in skills
        True
    """
    return sorted(SKILL_MAP.keys())


def format_skill_display(abbreviation: str, value: int) -> str:
    """
    Format a skill for display.

    Args:
        abbreviation: Skill abbreviation
        value: Skill value

    Returns:
        Formatted string (e.g., "Power (PO): 85")

    Example:
        >>> format_skill_display("PO", 85)
        'Power (PO): 85'
    """
    name = get_skill_name(abbreviation)
    return f"{name.replace('_', ' ').title()} ({abbreviation}): {value}"


def get_category_display_name(category: str) -> str:
    """
    Get a display-friendly category name.

    Args:
        category: Category key

    Returns:
        Title-cased category name

    Example:
        >>> get_category_display_name("hitting")
        'Hitting'
        >>> get_category_display_name("ground_balls")
        'Ground Balls'
    """
    return category.replace("_", " ").title()


# ---------- Validation Sets ----------

# For quick membership testing
ALL_SKILL_ABBRS: set[str] = set(SKILL_MAP.keys())
ALL_SKILL_NAMES: set[str] = set(SKILL_MAP.values())

# Skills by position type
BATTER_SKILLS: list[str] = SKILL_CATEGORIES["hitting"] + SKILL_CATEGORIES["general"]

PITCHER_SKILLS: list[str] = SKILL_CATEGORIES["pitching"] + SKILL_CATEGORIES["general"]

FIELDER_SKILLS: list[str] = SKILL_CATEGORIES["defense"] + SKILL_CATEGORIES["general"]
# # src/player/skill_map.py

# __author__ = "josh"

# SKILL_MAP = {
#     # hitting
#     "CL": "clutch",
#     "PO": "power",
#     "EY": "eye",
#     "CT": "contact",
#     "BR": "base_running",
#     "BU": "bunting",
#     # defense
#     "CA": "catching",
#     "IF": "infield",
#     "OF": "outfield",
#     "AR": "arm",
#     # pitching
#     "AC": "accuracy",
#     "ST": "stamina",
#     "RE": "recovery",
#     "GB": "ground_balls",
#     "KK": "strikes",
#     # general
#     "SP": "speed",
# }
