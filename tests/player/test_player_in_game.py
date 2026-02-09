# tests/player/test_player_in_game.py
"""
We want to enforce that PlayerInGame:

✔ References (does not copy) PlayerRecord
✔ Exposes immutable identity correctly
✔ Initializes clean game-only mutable state
✔ Can be safely reset
✔ Does not mutate PlayerRecord
✔ Delegates ratings correctly
✔ Is safe to stringify
"""

import pytest

import src.stats.stats as stats
from src.player.player_in_game import PlayerInGame
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


@pytest.fixture
def player_record():
    """Test fixtures"""
    skills = PlayerSkills(
        {
            "power": 50,
            "eye": 50,
            "contact": 50,
            "speed": 50,
            "base_running": 50,
            "arm": 50,
            "infield": 50,
            "outfield": 50,
            "catching": 50,
            "clutch": 50,
        }
    )

    return PlayerRecord(
        id="player123",
        first_name="John",
        last_name="Doe",
        bats="R",
        throws="R",
        position="cf",
        skills=skills,
    )


def test_player_in_game_references_record(player_record):
    """Snapshot semantics (record is referenced, not copied)"""
    pig = PlayerInGame(player_record)

    assert pig.record is player_record
    assert pig.id == player_record.id


def test_player_in_game_identity_fields(player_record):
    """Identity & immutable traits are copied correctly"""
    pig = PlayerInGame(player_record)

    assert pig.name == "John Doe"
    assert pig.bats == player_record.bats
    assert pig.throws == player_record.throws
    assert pig.skills is player_record.skills


def test_player_in_game_initial_state(player_record):
    """Game-only mutable state initializes cleanly"""    
    pig = PlayerInGame(player_record)

    assert isinstance(pig.game_stats, stats.GameStats)
    assert pig.pitcher_fatigue is None    
    assert pig.in_lineup is False
    assert pig.current_position is None
    assert pig.is_injured is False


def test_rate_player_creates_ratings(player_record):
    """
    rate_player() attaches ratings
    """
    pig = PlayerInGame(player_record)

    pig.rate_player()

    assert hasattr(pig, "ratings")
    assert isinstance(pig.ratings, dict)
    assert "overall_offense" in pig.ratings


def test_rate_player_does_not_mutate_record(player_record):
    """
    rate_player() attaches ratings (and does not mutate record)
    """
    pig = PlayerInGame(player_record)

    pig.rate_player()

    assert not hasattr(player_record, "ratings")


def test_init_game_stats_resets_stats(player_record):
    """init_game_stats() resets stats"""
    pig = PlayerInGame(player_record)

    old_stats = pig.game_stats
    pig.init_game_stats()

    assert pig.game_stats is not old_stats
    assert isinstance(pig.game_stats, stats.GameStats)


def test_player_in_game_str(player_record):
    """Safe stringification"""
    pig = PlayerInGame(player_record)

    assert str(pig) == "<Player John Doe>"


def test_player_in_game_mutation_is_local(player_record):
    """
    PlayerInGame is safe to mutate
    """
    pig = PlayerInGame(player_record)

    pig.fatigue = 5
    pig.in_lineup = True
    pig.current_position = "cf"
    pig.is_injured = True

    assert pig.fatigue == 5
    assert pig.in_lineup is True
    assert pig.current_position == "cf"
    assert pig.is_injured is True


def test_player_record_remains_immutable(player_record):
    """
    Guard test (future-proofing)

    This ensures PlayerInGame never mutates PlayerRecord:
    """
    pig = PlayerInGame(player_record)

    pig.fatigue = 99
    pig.rate_player()

    assert player_record.bats == "R"
    assert player_record.throws == "R"
    assert isinstance(player_record.skills, PlayerSkills)
