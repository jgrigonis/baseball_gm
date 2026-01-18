# tests/player/test_player_record.py
"""
What we want to guarantee

PlayerRecord must be:
✅ Immutable (frozen=True)
✅ A simple data holder (no mutation, no logic leaks)
✅ Correctly expose name
✅ Have a stable string representation
✅ Correctly construct from a CSV/db row
✅ Correctly delegate skills loading to PlayerSkills.from_db_row
"""

import pytest

from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


def test_player_record_fields_are_set():
    """Construction & attribute access"""
    skills = PlayerSkills({"power": 50})

    record = PlayerRecord(
        id="player123",
        first_name="John",
        last_name="Doe",
        bats="right",
        throws="left",
        position="cf",
        skills=skills,
    )

    assert record.id == "player123"
    assert record.first_name == "John"
    assert record.last_name == "Doe"
    assert record.bats == "right"
    assert record.throws == "left"
    assert record.skills is skills


def test_player_record_name_property():
    """Name property"""
    record = PlayerRecord(
        id="1",
        first_name="Mike",
        last_name="Trout",
        bats="right",
        throws="right",
        position="3b",
        skills=PlayerSkills({}),
    )

    assert record.name == "Mike Trout"


def test_player_record_str():
    """String representation"""
    record = PlayerRecord(
        id="1",
        first_name="Shohei",
        last_name="Ohtani",
        bats="left",
        throws="right",
        position="p",
        skills=PlayerSkills({}),
    )

    assert str(record) == "Shohei Ohtani"


def test_player_record_is_immutable():
    """
    Immutability (critical test)

    This enforces your architectural boundary.
    """
    record = PlayerRecord(
        id="1",
        first_name="Juan",
        last_name="Soto",
        bats="left",
        throws="right",
        position="rf",
        skills=PlayerSkills({}),
    )
    # optionally tighten this to FrozenInstanceError
    with pytest.raises(Exception):
        record.first_name = "Changed"


def test_player_record_from_row():
    """from_row builds correctly"""
    row = {
        "id": "abc123",
        "first_name": "Aaron",
        "last_name": "Judge",
        "bats": "right",
        "throws": "right",
        "power": 90,
        "contact": 75,
        "speed": 60,
        "position": "rf",
    }

    record = PlayerRecord.from_db_row(row)

    assert record.id == "abc123"
    assert record.first_name == "Aaron"
    assert record.last_name == "Judge"
    assert record.bats == "right"
    assert record.throws == "right"
    assert record.position == "rf"

    assert isinstance(record.skills, PlayerSkills)
    assert record.skills["power"] == 90
    assert record.skills["contact"] == 75
    assert record.skills["speed"] == 60


def test_player_record_does_not_allow_skill_mutation():
    """
    Guard: record never mutates skills

    This protects the record ↔ in-game boundary.
    """
    skills = PlayerSkills({"power": 50})
    record = PlayerRecord(
        id="1",
        first_name="Test",
        last_name="Player",
        bats="right",
        throws="right",
        position="lf",
        skills=skills,
    )

    with pytest.raises(TypeError):
        record.skills._skills["power"] = 99


def test_player_record_equality():
    """
    Equality is structural (dataclass behavior)
    """
    skills = PlayerSkills({"power": 50})

    a = PlayerRecord("1", "A", "B", "right", "right", "rf", skills)
    b = PlayerRecord("1", "A", "B", "right", "right", "rf", skills)

    assert a == b
