# tests/player/test_player_skills.py
"""
What we are testing (by design)

PlayerSkills must:
✅ Be immutable
✅ Behave like a read-only mapping
✅ Support [], in, items(), as_dict()
✅ Construct safely from partial rows
✅ Generate deterministic output when RNG is seeded
✅ Clamp generated stats to valid bounds
✅ Apply left-handed catcher rule correctly
❌ Never require attribute-style access
"""

import random
import pytest

from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS


def test_player_skills_basic_access():
    """Construction & mapping behavior"""
    skills = PlayerSkills({"power": 50, "speed": 60})

    assert skills["power"] == 50
    assert skills["speed"] == 60


def test_player_skills_no_attribute_access():
    """
    Mapping-only access (no attribute access)

    This enforces your architectural decision forever.
    """
    skills = PlayerSkills({"power": 50})

    with pytest.raises(AttributeError):
        _ = skills.power


def test_player_skills_as_dict_returns_copy():
    """.as_dict() returns a copy"""
    skills = PlayerSkills({"power": 50})

    d = skills.as_dict()
    d["power"] = 99

    assert skills["power"] == 50


def test_player_skills_is_immutable():
    """Immutability is enforced"""
    skills = PlayerSkills({"power": 50})

    with pytest.raises(TypeError):
        skills._skills["power"] = 99


def test_player_skills_repr():
    """__repr__ is stable and informative"""
    skills = PlayerSkills({"power": 50})

    rep = repr(skills)
    assert rep.startswith("PlayerSkills(")
    assert "power" in rep


def test_player_skills_from_row_fills_missing():
    """
    from_row fills missing skills with zero

    This is critical for CSV/db safety.
    """
    row = {"power": 80}

    skills = PlayerSkills.from_row(row)

    for skill in SKILLS:
        assert skill in skills

    assert skills["power"] == 80


def test_generate_stat_clamps_bounds():
    """
    generate_stat clamps to bounds

    We force extreme RNG output to ensure clamping works.
    """
    rng = random.Random(0)

    high = PlayerSkills.generate_stat(rng, minimum=1, maximum=100, mean=1000)
    low = PlayerSkills.generate_stat(rng, minimum=1, maximum=100, mean=-1000)

    assert 1 <= high <= 100
    assert 1 <= low <= 100


def test_generate_is_deterministic_with_seed():
    """
    generate is deterministic with seeded RNG

    This is huge for simulations and tests.
    """
    rng1 = random.Random(123)
    rng2 = random.Random(123)

    s1 = PlayerSkills.generate(rng1, position="cf", throws="right")
    s2 = PlayerSkills.generate(rng2, position="cf", throws="right")

    assert s1.as_dict() == s2.as_dict()


def test_left_handed_catcher_rule():
    """
    Left-handed catcher rule is enforced
    """
    rng = random.Random(42)

    skills = PlayerSkills.generate(rng, position="c", throws="left")

    assert skills["catching"] <= 20  # mean forced to 10
