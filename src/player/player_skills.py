from __future__ import annotations
import random
from types import MappingProxyType
from typing import Iterable


from src.player.positions import SKILLS, SKILL_TEMPLATE


class PlayerSkills(object):
    """
    Immutable value object representing a player's intrinsic skills.
    """

    def __init__(self, skills: dict[str, int]):
        self._skills = MappingProxyType(skills)

    def __getitem__(self, key: str) -> int:
        return self._skills[key]

    def __repr__(self):
        return f"PlayerSkills({dict(self._skills)})"

    def __contains__(self, key: str) -> bool:
        return key in self._skills

    def items(self) -> Iterable[tuple[str, int]]:
        return self._skills.items()

    def as_dict(self) -> dict[str, int]:
        return dict(self._skills)

    @classmethod
    def from_row(cls, row: dict[str, int]) -> PlayerSkills:
        # This guards against missing rows
        # We could enforce strictness later
        skills = {k: row.get(k, 0) for k in SKILLS}
        # skills = {k: row[k] for k in SKILLS.keys()}
        return cls(skills)

    @classmethod
    def generate(cls, rng: random.Random, position: str, throws: str) -> PlayerSkills:
        """
        Generate random skills, and characteristics, based on a
        position type.

        """
        skills = {}

        for skill, default_mean in SKILLS.items():
            mean = SKILL_TEMPLATE[position].get(skill, default_mean)
            skills[skill] = cls.generate_stat(rng=rng, mean=mean)

        # No left-handed catchers
        if throws == "left":
            skills["catching"] = cls.generate_stat(rng=rng, mean=10)

        return cls(skills)

    @classmethod
    def generate_stat(
        cls, rng: random.Random, minimum=1, maximum=100, mean=50, sigma=None
    ) -> int:
        """
        :param minimum: minimum allowable value for stat. Must be
            greater than 0
        :param maximum: maximum allowable value for stat. Must be
            greater than minimum
        :param mean: the mean value for the stat to be generated.
            Must be between minimum and maximum
        :param sigma: standard deviation. If unspecified, will vary
            based on min, max and mean.

        Generate one stat.  Generally, skills will have a mean
        value of 50.  The standard deviation, or sigma defaults to
        16.6667.  If you use a different mean, the sigma will shrink
        such that the 3rd standard deviation is the closer of max or
        min.  For example, if you use 70 for your mean, the sigma
        will be 10.  (100 - 70) / 3.

        """
        if sigma is None:
            if mean >= 50:
                sigma = (maximum - mean) / 3.0
            else:
                sigma = (mean - minimum) / 3.0
        stat = rng.gauss(mean, sigma)
        if stat > maximum:
            return maximum
        elif stat < minimum:
            return minimum
        return int(round(stat))
