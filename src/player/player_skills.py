# src/player/player_skills.py
"""
Player skill management.

PlayerSkills is an immutable value object that represents a player's
intrinsic abilities across all baseball skills (hitting, pitching, defense).

Skills are read as integers from 1-100. Each skill also keeps its exact
float value, so yearly aging can carry fractional progress forward instead
of losing it to rounding (see exact() and fractions()). Integer values are
the exact values rounded half up. Ranges:
- 1-30: Below average
- 30-50: Average
- 50-70: Above average
- 70-100: Elite

All skill values should match the skill names defined in SKILLS constant
from positions.py and skill_map.py.
"""

from __future__ import annotations
import math
import random
from types import MappingProxyType
from collections.abc import ItemsView, KeysView, ValuesView, Iterator

from src.player.player_skill_aging import SkillAging
from src.player.positions import SKILLS, SKILL_TEMPLATE
from src.player.skill_map import SKILL_MIN, SKILL_MAX
from src.player.player_constants import START_AGE
from src.types.rows import DbRow
from src.util.clamp import clamp

# Constants for skill generation
DEFAULT_SKILL_MEAN = 50
DEFAULT_SIGMA_DIVISOR = (
    3.5  # Tighter generation — ±3.5σ within range (99.95% of values)
)
# Increase to cluster skills closer to position means;
# decrease to produce more extreme outliers.

# Added to each position template mean when generating a 17-year-old.
# The aging curves give players more growth than the templates were tuned
# for, so 17-year-olds start a little lower; this keeps the skill levels of
# players at their peak (and of freshly generated leagues) where the game is
# balanced. Re-measure if the aging curves or talent caps change.
GENERATION_ADJUST: dict[str, float] = {
    "accuracy": -2.5,
    "stamina": -2.0,
    "recovery": -1.5,
    "ground_balls": -1.0,
    "strikes": -1.8,
    "clutch": -3.4,
    "speed": -1.5,
    "durability": 1.5,
    "power": -3.2,
    "eye": -3.0,
    "contact": -3.6,
    "base_running": -1.4,
    "bunting": -0.7,
    "catching": -3.5,
    "infield": -0.6,
    "outfield": -0.2,
    "arm": 1.3,
}


def _round_half_up(value: float) -> int:
    """Round to the nearest integer, halves up (round() rounds halves to even)."""
    return math.floor(value + 0.5)


# Breakout and crashout winters: (first age, last age, breakout chance,
# crashout chance), by the age a player is going into the winter. Young
# players break out or crash out about equally; past 30 a sudden collapse
# is far likelier than a late surge.
WINTER_SWINGS = [
    (20, 26, 0.04, 0.04),
    (27, 30, 0.015, 0.025),
    (31, 99, 0.005, 0.05),
]
# How far a swing moves each of the player's real skills, so his overall
# moves about as much.
SWING_SIZE = (4.0, 8.0)
# Skills below this are a player's non-skills (a pitcher's catching) and
# don't swing.
SWING_FLOOR_SKILL = 25


def winter_swing(age: int, rng: random.Random) -> float:
    """Points every real skill moves this winter: positive for a breakout,
    negative for a crashout, usually 0."""
    for first, last, up, down in WINTER_SWINGS:
        if first <= age <= last:
            roll = rng.random()
            if roll < up:
                return rng.uniform(*SWING_SIZE)
            if roll < up + down:
                return -rng.uniform(*SWING_SIZE)
            return 0.0
    return 0.0


class PlayerSkills:
    """
    Immutable value object representing a player's intrinsic skills.

    Skills are stored as a frozen mapping and cannot be modified after creation.
    Provides dictionary-like access to individual skills.

    Example:
        >>> skills = PlayerSkills({"power": 85, "speed": 60, ...})
        >>> skills["power"]
        85
        >>> "speed" in skills
        True
    """

    def __init__(
        self,
        skills: dict[str, int] | None = None,
        age: int = START_AGE,
        *,
        validate: bool = True,
        **kwargs,
    ):
        """
        Create PlayerSkills with validation.

        Args:
            skills: Dictionary of skill_name -> value (or pass as kwargs)
            validate: If True, validate all values are in range
            **kwargs: Individual skills as keyword arguments

        Raises:
            ValueError: If skill values are out of range (1-100)

        Example:
            >>> # Both styles work:
            >>> skills1 = PlayerSkills({"power": 85, "speed": 60})
            >>> skills2 = PlayerSkills(power=85, speed=60)
        """
        # Merge dict and kwargs
        if skills is None:
            skills = {}
        skills = {**skills, **kwargs}  # kwargs override dict values
        self.age = age

        normalized = {}
        exact = {}

        for skill_name in SKILLS:
            value = skills.get(skill_name, DEFAULT_SKILL_MEAN)

            try:
                exact_value = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"Skill '{skill_name}' has invalid value: {value}"
                ) from e
            value = _round_half_up(exact_value)

            # Validate range
            if validate and not (SKILL_MIN <= value <= SKILL_MAX):
                raise ValueError(
                    f"Skill '{skill_name}' value {value} out of range "
                    f"{SKILL_MIN}-{SKILL_MAX}"
                )

            normalized[skill_name] = value
            exact[skill_name] = exact_value

        self._skills = MappingProxyType(normalized)
        self._exact = MappingProxyType(exact)

    # ---------- Dictionary-like Interface ----------

    def __getitem__(self, key: str) -> int:
        """Get skill value by name."""
        return self._skills[key]

    def __contains__(self, key: str) -> bool:
        """Check if skill exists."""
        return key in self._skills

    def __iter__(self) -> Iterator[str]:
        """Iterate over skill names."""
        return iter(self._skills)

    def __len__(self) -> int:
        """Number of skills."""
        return len(self._skills)

    def get(self, key: str, default: int | None = None) -> int | None:
        """Get skill value with optional default."""
        return self._skills.get(key, default)

    def keys(self) -> KeysView[str]:
        """Get all skill names."""
        return self._skills.keys()

    def values(self) -> ValuesView[int]:
        """Get all skill values."""
        return self._skills.values()

    def items(self) -> ItemsView[str, int]:
        """Get all (skill_name, value) pairs."""
        return self._skills.items()

    def as_dict(self) -> dict[str, int]:
        """Return a mutable copy of skills as a dictionary."""
        return dict(self._skills)

    # ---------- Exact (fractional) values ----------

    def exact(self, key: str) -> float:
        """The skill's exact value, including progress below one point."""
        return self._exact[key]

    def fractions(self) -> dict[str, float]:
        """
        Each skill's exact value minus its integer value, in [-0.5, 0.5).
        Stored next to the integer skills so aging keeps partial progress.
        """
        return {k: self._exact[k] - self._skills[k] for k in self._skills}

    def with_fractions(self, fractions: dict[str, float] | None) -> PlayerSkills:
        """
        A copy whose exact values are the integer skills plus *fractions*
        (as saved by fractions()). Skills missing from *fractions* stay whole.
        """
        if not fractions:
            return self
        exact = {
            k: float(clamp(v + fractions.get(k, 0.0), SKILL_MIN, SKILL_MAX))
            for k, v in self._skills.items()
        }
        return PlayerSkills(exact, age=self.age)

    # ---------- Comparison ----------

    def __eq__(self, other: object) -> bool:
        """Check equality with another PlayerSkills object."""
        if not isinstance(other, PlayerSkills):
            return NotImplemented
        return self._skills == other._skills

    def __hash__(self) -> int:
        """Hash for use in sets/dicts."""
        return hash(tuple(sorted(self._skills.items())))

    # ---------- String Representation ----------

    def __repr__(self) -> str:
        """Developer-friendly representation."""
        return f"PlayerSkills({dict(self._skills)})"

    def __str__(self) -> str:
        """Human-readable representation showing all skills."""
        from src.player.skill_map import (
            get_skill_abbr,
            get_skill_category,
            SKILL_CATEGORIES,
        )

        lines = []
        for category in ["hitting", "pitching", "defense", "general"]:
            if category not in SKILL_CATEGORIES:
                continue

            category_lines = []

            for skill_name, value in sorted(self._skills.items()):
                try:
                    abbr = get_skill_abbr(skill_name)
                    if get_skill_category(abbr) == category:
                        category_lines.append(f"  {skill_name:15s}: {value:3d}")
                except ValueError:
                    # Skip skills not in SKILL_MAP
                    pass

            if category_lines:
                lines.append(f"\n{category.upper()}:")
                lines.extend(category_lines)

        return "\n".join(lines)

    # ---------- Aggregate Queries ----------

    def average(self) -> float:
        """
        Get average skill value across all skills.

        Returns:
            Mean of all skill values

        Example:
            >>> skills = PlayerSkills({"power": 80, "speed": 60})
            >>> skills.average()
            70.0
        """
        return sum(self._skills.values()) / len(self._skills)

    def total(self) -> int:
        """
        Get total of all skill values.

        Returns:
            Sum of all skill values
        """
        return sum(self._skills.values())

    def get_category_skills(self, category: str) -> dict[str, int]:
        """
        Get all skills in a specific category.

        Args:
            category: One of "hitting", "defense", "pitching", "general"

        Returns:
            Dictionary of skill_name -> value for that category

        Raises:
            ValueError: If category is invalid

        Example:
            >>> hitting_skills = skills.get_category_skills("hitting")
            >>> hitting_skills["power"]
            85
        """
        from src.player.skill_map import get_skill_abbr, get_skill_category

        result = {}
        for name, value in self._skills.items():
            try:
                # Convert full name to abbreviation for category lookup
                abbr = get_skill_abbr(name)
                if get_skill_category(abbr) == category:
                    result[name] = value
            except ValueError:
                # Skip skills not in SKILL_MAP
                continue

        return result

    # ---------- Factory Methods ----------

    @classmethod
    def from_db_row(cls, row: DbRow) -> PlayerSkills:
        """
        Create PlayerSkills from a database row.

        Args:
            row: Database row with skill columns

        Returns:
            PlayerSkills instance

        Note:
            Missing skills default to 50 (league average)
        """
        row_dict = dict(row)
        skills = {k: row_dict.get(k, DEFAULT_SKILL_MEAN) for k in SKILLS}
        age = row_dict.get("age", START_AGE)
        return cls(skills, age=age)

    @classmethod
    def generate(
        cls,
        rng: random.Random,
        position: str,
        throws: str | None = None,
        age: int = START_AGE,
    ) -> PlayerSkills:
        """
        Generate random skills based on position.

        Uses position-specific skill templates to create realistic
        skill distributions. For example, shortstops will have high
        speed and infield skills, while power hitters have high power.

        Args:
            rng: Random number generator for reproducibility
            position: Position code (e.g., "ss", "sp", "cf")
            throws: Throwing hand ("left" or "right"), optional
            age: Age of the player
        Returns:
            PlayerSkills instance with randomly generated values

        Example:
            >>> rng = random.Random(42)
            >>> skills = PlayerSkills.generate(rng, "ss", "right")
            >>> skills["infield"] > 60  # Shortstops have good defense
            True
        """
        skills = {}

        # Generate each skill based on position template
        for skill_name, default_mean in SKILLS.items():
            mean = SKILL_TEMPLATE[position].get(skill_name, default_mean)
            mean = clamp(
                mean + GENERATION_ADJUST.get(skill_name, 0.0), SKILL_MIN, SKILL_MAX
            )
            skills[skill_name] = cls.generate_stat(rng=rng, mean=mean)

        # Apply position-specific restrictions
        cls._apply_position_restrictions(skills, position, throws, rng)

        return cls(
            skills, age=age, validate=False
        )  # Already validated in generate_stat

    @classmethod
    def _apply_position_restrictions(
        cls,
        skills: dict[str, int],
        position: str,
        throws: str | None,
        rng: random.Random,
    ) -> None:
        """
        Apply position-specific skill restrictions.

        Args:
            skills: Skills dictionary to modify in-place
            position: Position code
            throws: Throwing hand
            rng: Random number generator
        """
        # No left-handed catchers (extremely rare in real baseball)
        if position == "c" and throws == "L":
            skills["catching"] = cls.generate_stat(rng=rng, mean=10)

    @classmethod
    def generate_stat(
        cls,
        rng: random.Random,
        mean: int = DEFAULT_SKILL_MEAN,
        minimum: int = SKILL_MIN,
        maximum: int = SKILL_MAX,
        sigma: float | None = None,
    ) -> int:
        """
        Generate a single skill value using normal distribution.

        Uses Gaussian distribution with automatic sigma calculation to ensure
        99.7% of values fall within the valid range.

        Args:
            rng: Random number generator
            mean: Target mean value (default 50)
            minimum: Minimum allowed value (default 1)
            maximum: Maximum allowed value (default 100)
            sigma: Standard deviation. If None, auto-calculated to fit range

        Returns:
            Integer skill value clamped to [minimum, maximum]

        Example:
            >>> rng = random.Random(42)
            >>> PlayerSkills.generate_stat(rng, mean=70)
            73  # Will be close to 70 with some variation
        """
        # Validate inputs
        if not (minimum < maximum):
            raise ValueError(f"minimum ({minimum}) must be < maximum ({maximum})")
        if not (minimum <= mean <= maximum):
            raise ValueError(f"mean ({mean}) must be between {minimum} and {maximum}")

        # Auto-calculate sigma to ensure ~99.7% of values are in range
        if sigma is None:
            # Use the closer bound to avoid exceeding range
            distance_to_max = maximum - mean
            distance_to_min = mean - minimum
            sigma = min(distance_to_max, distance_to_min) / DEFAULT_SIGMA_DIVISOR

        # Generate value from normal distribution
        stat = rng.gauss(mean, sigma)

        # Clamp to valid range
        if stat > maximum:
            return maximum
        elif stat < minimum:
            return minimum

        return int(round(stat))

    # ---------- Serialization ----------

    def to_db_dict(self) -> dict[str, int]:
        """
        Convert to dictionary suitable for database storage.

        Returns:
            Dictionary with full skill names as keys
        """
        d = self.as_dict()
        d["age"] = self.age
        return d

    def age_to(
        self,
        age: int,
        from_age: int = START_AGE,
        coaching: float = 1.0,
        rng: random.Random | None = None,
        caps: dict[str, int] | None = None,
        swings: bool = False,
    ) -> PlayerSkills:
        """
        Simulate skill progression from START_AGE to the given age.
        Returns a new PlayerSkills instance — does not mutate self.

        Args:
            age:      Target age to age the player to
            coaching: Coaching quality multiplier (1.0 = neutral)
            rng:      Seeded RNG for reproducibility
            caps:     Per-player talent caps from player_talent_caps table.
                      If None, no cap dampening is applied (legacy behaviour).
                      Keys are full skill names e.g. "contact", "stamina".
                      A breakout or crashout winter (winter_swing) moves
                      the caps in place, so save them if they changed.
            swings:   Roll for breakout and crashout winters. Only real
                      offseasons do; generated players (opening rosters,
                      draft classes, backstory) keep year one's spread.
        """
        if age <= from_age:
            return self
        rng = rng or random.Random()

        # Helper: look up cap for a skill, None if not provided
        def cap(skill_name: str) -> int | None:
            return caps.get(skill_name) if caps else None

        # Work with exact floats so partial progress carries year to year
        s = dict(self._exact)
        SA = SkillAging()

        for current_age in range(from_age, age):
            s["speed"] += SA.delta_SP(current_age, s["speed"], rng, cap("speed"))
            s["power"] += SA.delta_PO(current_age, s["power"], rng, cap("power"))
            s["arm"] += SA.delta_AR(current_age, s["arm"], rng, cap("arm"))
            s["strikes"] += SA.delta_KK(current_age, s["strikes"], rng, cap("strikes"))
            s["clutch"] += SA.delta_CL(current_age, s["clutch"], rng, cap("clutch"))
            s["eye"] += SA.delta_EY(current_age, s["eye"], rng, coaching, cap("eye"))
            s["contact"] += SA.delta_CT(
                current_age, s["contact"], rng, coaching, cap("contact")
            )
            s["base_running"] += SA.delta_BR(
                current_age, s["base_running"], rng, coaching, cap("base_running")
            )
            s["bunting"] += SA.delta_BU(
                current_age, s["bunting"], rng, coaching, cap("bunting")
            )
            s["catching"] += SA.delta_CA(
                current_age, s["catching"], rng, coaching, cap("catching")
            )
            s["infield"] += SA.delta_IF(
                current_age, s["infield"], rng, coaching, cap("infield")
            )
            s["outfield"] += SA.delta_OF(
                current_age, s["outfield"], rng, coaching, cap("outfield")
            )
            s["ground_balls"] += SA.delta_GB(
                current_age, s["ground_balls"], rng, coaching, cap("ground_balls")
            )
            s["accuracy"] += SA.delta_AC(
                current_age, s["accuracy"], rng, coaching, cap("accuracy")
            )
            s["stamina"] += SA.delta_ST(
                current_age, s["stamina"], rng, coaching, cap("stamina")
            )
            s["recovery"] += SA.delta_RE(
                current_age, s["recovery"], rng, coaching, cap("recovery")
            )
            s["durability"] += SA.delta_DU(
                current_age, s["durability"], rng, coaching, cap("durability")
            )

            # A rare breakout or crashout winter moves every real skill
            # together, so the player's overall jumps, not just one skill.
            swing = winter_swing(current_age, rng) if swings else 0.0
            if swing:
                for k in s:
                    if s[k] >= SWING_FLOOR_SKILL:
                        s[k] += swing
                        # The ceiling moves too, so the jump lasts instead
                        # of eating into the growth he had left.
                        if caps and k in caps:
                            caps[k] = int(clamp(round(caps[k] + swing), 1, 100))

            for k in s:
                s[k] = float(clamp(s[k], 1, 100))

        return PlayerSkills(s, age=age)
