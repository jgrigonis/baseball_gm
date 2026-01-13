# tests/player/test_skill_map.py
"""
Tests here are mapping integrity tests, not value tests.
"""
from src.player.skill_map import SKILL_MAP
from src.player.positions import SKILLS


def test_skill_map_targets_are_valid_skills():
    """All mapped values are valid skills"""
    for abbr, skill in SKILL_MAP.items():
        assert skill in SKILLS, f"{abbr} maps to unknown skill '{skill}'"


def test_skill_map_keys_are_uppercase_strings():
    for key in SKILL_MAP:
        assert isinstance(key, str)
        assert key.isupper()


def test_skill_map_values_are_lowercase_strings():
    for value in SKILL_MAP.values():
        assert isinstance(value, str)
        assert value == value.lower()


def test_skill_map_values_equals_SKILLS():
    domain_keys = []
    for csv_key, domain_key in SKILL_MAP.items():
        domain_keys.append(domain_key)
        print(f"{csv_key} {domain_key}")

    for skill in SKILLS:
        print(skill)

    assert set(domain_keys) == set(SKILLS)
