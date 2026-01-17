# src/player/player_skills.py
"""
Player skill management.

PlayerSkills is an immutable value object that represents a player's
intrinsic abilities across all baseball skills (hitting, pitching, defense).

Skills are stored as integers from 1-100, where:
- 1-30: Below average
- 30-50: Average
- 50-70: Above average
- 70-100: Elite

All skill values should match the skill names defined in SKILLS constant
from positions.py and skill_map.py.
"""

from __future__ import annotations
import random
from types import MappingProxyType
from typing import ItemsView, KeysView, ValuesView, Iterator

from src.player.positions import SKILLS, SKILL_TEMPLATE
from src.player.skill_map import SKILL_MAP, SKILL_MIN, SKILL_MAX
from src.types.rows import CsvRow, DbRow

# Constants for skill generation
DEFAULT_SKILL_MEAN = 50
DEFAULT_SIGMA_DIVISOR = 3.0  # For 99.7% of values within range (±3σ)


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

    def __init__(self, skills: dict[str, int], *, validate: bool = True):
        """
        Create PlayerSkills with validation.

        Args:
            skills: Dictionary of skill_name -> value
            validate: If True, validate all values are in range

        Raises:
            ValueError: If skill values are out of range (1-100)
        """
        normalized = {}

        for skill_name in SKILLS:
            value = skills.get(skill_name, DEFAULT_SKILL_MEAN)

            # Convert to int if needed
            if not isinstance(value, int):
                try:
                    value = int(value)
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"Skill '{skill_name}' has invalid value: {value}"
                    ) from e

            # Validate range
            if validate and not (SKILL_MIN <= value <= SKILL_MAX):
                raise ValueError(
                    f"Skill '{skill_name}' value {value} out of range "
                    f"{SKILL_MIN}-{SKILL_MAX}"
                )

            normalized[skill_name] = value

        self._skills = MappingProxyType(normalized)

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
        skills = {k: row.get(k, DEFAULT_SKILL_MEAN) for k in SKILLS}
        return cls(skills)

    @classmethod
    def from_csv_row(cls, row: CsvRow) -> PlayerSkills:
        """
        Create PlayerSkills from a CSV row.

        Args:
            row: CSV row with abbreviated skill columns (e.g., "PO", "SP")

        Returns:
            PlayerSkills instance

        Raises:
            ValueError: If required columns are missing or invalid

        Example:
            >>> row = {"PO": "85", "SP": "60", ...}
            >>> skills = PlayerSkills.from_csv_row(row)
        """
        skills = {}

        for csv_key, domain_key in SKILL_MAP.items():
            if csv_key not in row:
                raise ValueError(f"Missing required CSV column: '{csv_key}'")

            try:
                skills[domain_key] = int(row[csv_key])
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid value for '{csv_key}': {row[csv_key]}"
                ) from e

        return cls(skills)

    @classmethod
    def generate(
        cls,
        rng: random.Random,
        position: str,
        throws: str | None = None,
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
            skills[skill_name] = cls.generate_stat(rng=rng, mean=mean)

        # Apply position-specific restrictions
        cls._apply_position_restrictions(skills, position, throws, rng)

        return cls(skills, validate=False)  # Already validated in generate_stat

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
        if position == "c" and throws == "left":
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
        return self.as_dict()

    def to_csv_dict(self) -> dict[str, int]:
        """
        Convert to dictionary suitable for CSV export.

        Returns:
            Dictionary with abbreviated skill names (e.g., "PO", "SP")
        """
        from src.player.skill_map import get_skill_abbr

        csv_dict = {}
        for skill_name, value in self._skills.items():
            try:
                abbr = get_skill_abbr(skill_name)
                csv_dict[abbr] = value
            except ValueError:
                # Skip skills not in SKILL_MAP
                continue

        return csv_dict


# # src/player/player_skills.py
# """
# Player skill management.

# PlayerSkills is an immutable value object that represents a player's
# intrinsic abilities across all baseball skills (hitting, pitching, defense).

# Skills are stored as integers from 1-100, where:
# - 1-30: Below average
# - 30-50: Average
# - 50-70: Above average
# - 70-100: Elite

# All skill values should match the skill names defined in SKILLS constant
# from positions.py and skill_map.py.
# """

# from __future__ import annotations
# import random
# from types import MappingProxyType
# from typing import ItemsView, KeysView, ValuesView, Iterator

# from src.player.positions import SKILLS, SKILL_TEMPLATE
# from src.player.skill_map import SKILL_MAP, SKILL_MIN, SKILL_MAX
# from src.types.rows import CsvRow, DbRow

# # Constants for skill generation
# DEFAULT_SKILL_MEAN = 50
# DEFAULT_SIGMA_DIVISOR = 3.0  # For 99.7% of values within range (±3σ)


# class PlayerSkills:
#     """
#     Immutable value object representing a player's intrinsic skills.

#     Skills are stored as a frozen mapping and cannot be modified after creation.
#     Provides dictionary-like access to individual skills.

#     Example:
#         >>> skills = PlayerSkills({"power": 85, "speed": 60, ...})
#         >>> skills["power"]
#         85
#         >>> "speed" in skills
#         True
#     """

#     def __init__(self, skills: dict[str, int], *, validate: bool = True):
#         """
#         Create PlayerSkills with validation.

#         Args:
#             skills: Dictionary of skill_name -> value
#             validate: If True, validate all values are in range

#         Raises:
#             ValueError: If skill values are out of range (1-100)
#         """
#         normalized = {}

#         for skill_name in SKILLS:
#             value = skills.get(skill_name, DEFAULT_SKILL_MEAN)

#             # Convert to int if needed
#             if not isinstance(value, int):
#                 try:
#                     value = int(value)
#                 except (TypeError, ValueError) as e:
#                     raise ValueError(
#                         f"Skill '{skill_name}' has invalid value: {value}"
#                     ) from e

#             # Validate range
#             if validate and not (SKILL_MIN <= value <= SKILL_MAX):
#                 raise ValueError(
#                     f"Skill '{skill_name}' value {value} out of range "
#                     f"{SKILL_MIN}-{SKILL_MAX}"
#                 )

#             normalized[skill_name] = value

#         self._skills = MappingProxyType(normalized)

#     # ---------- Dictionary-like Interface ----------

#     def __getitem__(self, key: str) -> int:
#         """Get skill value by name."""
#         return self._skills[key]

#     def __contains__(self, key: str) -> bool:
#         """Check if skill exists."""
#         return key in self._skills

#     def __iter__(self) -> Iterator[str]:
#         """Iterate over skill names."""
#         return iter(self._skills)

#     def __len__(self) -> int:
#         """Number of skills."""
#         return len(self._skills)

#     def get(self, key: str, default: int | None = None) -> int | None:
#         """Get skill value with optional default."""
#         return self._skills.get(key, default)

#     def keys(self) -> KeysView[str]:
#         """Get all skill names."""
#         return self._skills.keys()

#     def values(self) -> ValuesView[int]:
#         """Get all skill values."""
#         return self._skills.values()

#     def items(self) -> ItemsView[str, int]:
#         """Get all (skill_name, value) pairs."""
#         return self._skills.items()

#     def as_dict(self) -> dict[str, int]:
#         """Return a mutable copy of skills as a dictionary."""
#         return dict(self._skills)

#     # ---------- Comparison ----------

#     def __eq__(self, other: object) -> bool:
#         """Check equality with another PlayerSkills object."""
#         if not isinstance(other, PlayerSkills):
#             return NotImplemented
#         return self._skills == other._skills

#     def __hash__(self) -> int:
#         """Hash for use in sets/dicts."""
#         return hash(tuple(sorted(self._skills.items())))

#     # ---------- String Representation ----------

#     def __repr__(self) -> str:
#         """Developer-friendly representation."""
#         return f"PlayerSkills({dict(self._skills)})"

#     def __str__(self) -> str:
#         """Human-readable representation showing all skills."""
#         from src.player.skill_map import get_skill_category, SKILL_CATEGORIES, get_skill_abbr

#         lines = []
#         for category in ["hitting", "pitching", "defense", "general"]:
#             if category not in SKILL_CATEGORIES:
#                 continue

#             lines.append(f"\n{category.upper()}:")
#             for skill_name, value in sorted(self._skills.items()):
#                 try:
#                     skill_abbr = get_skill_abbr(skill_name)
#                 except:
#                     pass
#                 try:
#                     if get_skill_category(skill_abbr) == category:
#                         lines.append(f"  {skill_abbr:15s}: {value:3d}")
#                 except:
#                     # Skip skills not in categories
#                     pass

#         return "\n".join(lines)

#     # ---------- Aggregate Queries ----------

#     def average(self) -> float:
#         """
#         Get average skill value across all skills.

#         Returns:
#             Mean of all skill values

#         Example:
#             >>> skills = PlayerSkills({"power": 80, "speed": 60})
#             >>> skills.average()
#             70.0
#         """
#         return sum(self._skills.values()) / len(self._skills)

#     def total(self) -> int:
#         """
#         Get total of all skill values.

#         Returns:
#             Sum of all skill values
#         """
#         return sum(self._skills.values())

#     def get_category_skills(self, category: str) -> dict[str, int]:
#         """
#         Get all skills in a specific category.

#         Args:
#             category: One of "hitting", "defense", "pitching", "general"

#         Returns:
#             Dictionary of skill_name -> value for that category

#         Raises:
#             ValueError: If category is invalid

#         Example:
#             >>> hitting_skills = skills.get_category_skills("hitting")
#             >>> hitting_skills["power"]
#             85
#         """
#         from src.player.skill_map import get_skill_category

#         return {
#             name: value
#             for name, value in self._skills.items()
#             if get_skill_category(name) == category
#         }

#     # ---------- Factory Methods ----------

#     @classmethod
#     def from_db_row(cls, row: DbRow) -> PlayerSkills:
#         """
#         Create PlayerSkills from a database row.

#         Args:
#             row: Database row with skill columns

#         Returns:
#             PlayerSkills instance

#         Note:
#             Missing skills default to 50 (league average)
#         """
#         skills = {k: row.get(k, DEFAULT_SKILL_MEAN) for k in SKILLS}
#         return cls(skills)

#     @classmethod
#     def from_csv_row(cls, row: CsvRow) -> PlayerSkills:
#         """
#         Create PlayerSkills from a CSV row.

#         Args:
#             row: CSV row with abbreviated skill columns (e.g., "PO", "SP")

#         Returns:
#             PlayerSkills instance

#         Raises:
#             ValueError: If required columns are missing or invalid

#         Example:
#             >>> row = {"PO": "85", "SP": "60", ...}
#             >>> skills = PlayerSkills.from_csv_row(row)
#         """
#         skills = {}

#         for csv_key, domain_key in SKILL_MAP.items():
#             if csv_key not in row:
#                 raise ValueError(f"Missing required CSV column: '{csv_key}'")

#             try:
#                 skills[domain_key] = int(row[csv_key])
#             except (ValueError, TypeError) as e:
#                 raise ValueError(
#                     f"Invalid value for '{csv_key}': {row[csv_key]}"
#                 ) from e

#         return cls(skills)

#     @classmethod
#     def generate(
#         cls,
#         rng: random.Random,
#         position: str,
#         throws: str | None = None,
#     ) -> PlayerSkills:
#         """
#         Generate random skills based on position.

#         Uses position-specific skill templates to create realistic
#         skill distributions. For example, shortstops will have high
#         speed and infield skills, while power hitters have high power.

#         Args:
#             rng: Random number generator for reproducibility
#             position: Position code (e.g., "ss", "sp", "cf")
#             throws: Throwing hand ("left" or "right"), optional

#         Returns:
#             PlayerSkills instance with randomly generated values

#         Example:
#             >>> rng = random.Random(42)
#             >>> skills = PlayerSkills.generate(rng, "ss", "right")
#             >>> skills["infield"] > 60  # Shortstops have good defense
#             True
#         """
#         skills = {}

#         # Generate each skill based on position template
#         for skill_name, default_mean in SKILLS.items():
#             mean = SKILL_TEMPLATE[position].get(skill_name, default_mean)
#             skills[skill_name] = cls.generate_stat(rng=rng, mean=mean)

#         # Apply position-specific restrictions
#         cls._apply_position_restrictions(skills, position, throws, rng)

#         return cls(skills, validate=False)  # Already validated in generate_stat

#     @classmethod
#     def _apply_position_restrictions(
#         cls,
#         skills: dict[str, int],
#         position: str,
#         throws: str | None,
#         rng: random.Random,
#     ) -> None:
#         """
#         Apply position-specific skill restrictions.

#         Args:
#             skills: Skills dictionary to modify in-place
#             position: Position code
#             throws: Throwing hand
#             rng: Random number generator
#         """
#         # No left-handed catchers (extremely rare in real baseball)
#         if position == "c" and throws == "left":
#             skills["catching"] = cls.generate_stat(rng=rng, mean=10)

#     @classmethod
#     def generate_stat(
#         cls,
#         rng: random.Random,
#         mean: int = DEFAULT_SKILL_MEAN,
#         minimum: int = SKILL_MIN,
#         maximum: int = SKILL_MAX,
#         sigma: float | None = None,
#     ) -> int:
#         """
#         Generate a single skill value using normal distribution.

#         Uses Gaussian distribution with automatic sigma calculation to ensure
#         99.7% of values fall within the valid range.

#         Args:
#             rng: Random number generator
#             mean: Target mean value (default 50)
#             minimum: Minimum allowed value (default 1)
#             maximum: Maximum allowed value (default 100)
#             sigma: Standard deviation. If None, auto-calculated to fit range

#         Returns:
#             Integer skill value clamped to [minimum, maximum]

#         Example:
#             >>> rng = random.Random(42)
#             >>> PlayerSkills.generate_stat(rng, mean=70)
#             73  # Will be close to 70 with some variation
#         """
#         # Validate inputs
#         if not (minimum < maximum):
#             raise ValueError(f"minimum ({minimum}) must be < maximum ({maximum})")
#         if not (minimum <= mean <= maximum):
#             raise ValueError(f"mean ({mean}) must be between {minimum} and {maximum}")

#         # Auto-calculate sigma to ensure ~99.7% of values are in range
#         if sigma is None:
#             # Use the closer bound to avoid exceeding range
#             distance_to_max = maximum - mean
#             distance_to_min = mean - minimum
#             sigma = min(distance_to_max, distance_to_min) / DEFAULT_SIGMA_DIVISOR

#         # Generate value from normal distribution
#         stat = rng.gauss(mean, sigma)

#         # Clamp to valid range
#         if stat > maximum:
#             return maximum
#         elif stat < minimum:
#             return minimum

#         return int(round(stat))

#     # ---------- Serialization ----------

#     def to_db_dict(self) -> dict[str, int]:
#         """
#         Convert to dictionary suitable for database storage.

#         Returns:
#             Dictionary with full skill names as keys
#         """
#         return self.as_dict()

#     def to_csv_dict(self) -> dict[str, int]:
#         """
#         Convert to dictionary suitable for CSV export.

#         Returns:
#             Dictionary with abbreviated skill names (e.g., "PO", "SP")
#         """
#         from src.player.skill_map import get_skill_abbr

#         csv_dict = {}
#         for skill_name, value in self._skills.items():
#             try:
#                 abbr = get_skill_abbr(skill_name)
#                 csv_dict[abbr] = value
#             except ValueError:
#                 # Skip skills not in SKILL_MAP
#                 continue

#         return csv_dict

# # src/player/player_skills.py
# from __future__ import annotations
# import random
# from types import MappingProxyType
# from typing import Iterable


# from src.player.positions import SKILLS, SKILL_TEMPLATE
# from src.player.skill_map import SKILL_MAP
# from src.types.rows import CsvRow, DbRow


# class PlayerSkills(object):
#     """
#     Immutable value object representing a player's intrinsic skills.
#     """

#     def __init__(self, skills: dict[str, int]):
#         normalized = {k: int(skills.get(k, 0)) for k in SKILLS}
#         self._skills = MappingProxyType(normalized)
#         # self._skills = MappingProxyType(skills)

#     def __getitem__(self, key: str) -> int:
#         return self._skills[key]

#     def __repr__(self):
#         return f"PlayerSkills({dict(self._skills)})"

#     def __contains__(self, key: str) -> bool:
#         return key in self._skills

#     def items(self) -> Iterable[tuple[str, int]]:
#         return self._skills.items()

#     def as_dict(self) -> dict[str, int]:
#         return dict(self._skills)

#     @classmethod
#     def from_db_row(cls, row: DbRow) -> PlayerSkills:
#         # This guards against missing rows
#         # We could enforce strictness later
#         skills = {k: row.get(k, 0) for k in SKILLS}
#         # skills = {k: row[k] for k in SKILLS.keys()}
#         return cls(skills)

#     @classmethod
#     def from_csv_row(cls, row: CsvRow) -> "PlayerSkills":
#         skills = {
#             domain_key: int(row[csv_key]) for csv_key, domain_key in SKILL_MAP.items()
#         }
#         return cls(skills)

#     @classmethod
#     def generate(cls, rng: random.Random, position: str, throws: str) -> PlayerSkills:
#         """
#         Generate random skills, and characteristics, based on a
#         position type.

#         """
#         skills = {}

#         for skill, default_mean in SKILLS.items():
#             mean = SKILL_TEMPLATE[position].get(skill, default_mean)
#             skills[skill] = cls.generate_stat(rng=rng, mean=mean)

#         # No left-handed catchers
#         if throws == "left":
#             skills["catching"] = cls.generate_stat(rng=rng, mean=10)

#         return cls(skills)

#     @classmethod
#     def generate_stat(
#         cls, rng: random.Random, minimum=1, maximum=100, mean=50, sigma=None
#     ) -> int:
#         """
#         :param minimum: minimum allowable value for stat. Must be
#             greater than 0
#         :param maximum: maximum allowable value for stat. Must be
#             greater than minimum
#         :param mean: the mean value for the stat to be generated.
#             Must be between minimum and maximum
#         :param sigma: standard deviation. If unspecified, will vary
#             based on min, max and mean.

#         Generate one stat.  Generally, skills will have a mean
#         value of 50.  The standard deviation, or sigma defaults to
#         16.6667.  If you use a different mean, the sigma will shrink
#         such that the 3rd standard deviation is the closer of max or
#         min.  For example, if you use 70 for your mean, the sigma
#         will be 10.  (100 - 70) / 3.

#         """
#         if sigma is None:
#             if mean >= 50:
#                 sigma = (maximum - mean) / 3.0
#             else:
#                 sigma = (mean - minimum) / 3.0
#         stat = rng.gauss(mean, sigma)
#         if stat > maximum:
#             return maximum
#         elif stat < minimum:
#             return minimum
#         return int(round(stat))
