# tests/player/test_skill_map.py
"""
Tests here are mapping integrity tests, not value tests.
"""


def test_skill_map_targets_are_valid_skills():
    """All mapped values are valid skills"""
    from src.player.skill_map import SKILL_MAP
    from src.player.positions import SKILLS

    for abbr, skill in SKILL_MAP.items():
        assert skill in SKILLS, f"{abbr} maps to unknown skill '{skill}'"


def test_skill_map_keys_are_uppercase_strings():
    from src.player.skill_map import SKILL_MAP

    for key in SKILL_MAP:
        assert isinstance(key, str)
        assert key.isupper()


def test_skill_map_values_are_lowercase_strings():
    from src.player.skill_map import SKILL_MAP

    for value in SKILL_MAP.values():
        assert isinstance(value, str)
        assert value == value.lower()
