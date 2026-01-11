# tests/player/test_positions.py
"""
positions.py is mostly declarative data, not behavior. Do not unit
test the contents (those are design choices), but do test the
invariants that other code relies on.

Think of these as schema / contract tests, not logic tests.
"""


def test_every_position_has_name():
    """Every position has a name"""
    from src.player.positions import POSITIONS, POSITION_NAME

    for pos in POSITIONS:
        assert pos in POSITION_NAME


def test_position_templates_cover_all_positions():
    """
    POSITION_TEMPLATES covers all positions
    Generators assume this.
    """
    from src.player.positions import POSITIONS, POSITION_TEMPLATES

    for pos in POSITIONS:
        assert pos in POSITION_TEMPLATES


import pytest


def test_position_templates_is_immutable():
    """
    POSITION_TEMPLATES is immutable
    Critical architectural guarantee.
    """
    from src.player.positions import POSITION_TEMPLATES

    with pytest.raises(TypeError):
        POSITION_TEMPLATES["cf"] = {}


def test_skills_is_immutable():
    """
    SKILLS is immutable
    We rely on this elsewhere.
    """
    from src.player.positions import SKILLS

    with pytest.raises(TypeError):
        SKILLS["power"] = 999


def test_skill_templates_only_use_known_skills():
    """Every SKILL_TEMPLATE key is a valid skill"""
    from src.player.positions import SKILL_TEMPLATE, SKILLS

    for pos, template in SKILL_TEMPLATE.items():
        for skill in template:
            assert skill in SKILLS, f"{pos} uses unknown skill '{skill}'"


def test_skill_templates_only_use_known_positions():
    """
    Every SKILL_TEMPLATE position is valid
    Prevents orphan entries.
    """
    from src.player.positions import SKILL_TEMPLATE, POSITIONS

    for pos in SKILL_TEMPLATE:
        assert pos in POSITIONS


def test_every_position_has_skill_template():
    """
    Every position has some skill override
    Prevents accidental empty templates.
    """
    from src.player.positions import POSITIONS, SKILL_TEMPLATE

    for pos in POSITIONS:
        assert pos in SKILL_TEMPLATE
        assert isinstance(SKILL_TEMPLATE[pos], dict)
