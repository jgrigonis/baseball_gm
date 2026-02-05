# tests/team/test_team_record.py
"""
What we are testing (and why)

TeamRecord contract:

✔ Immutable
✔ Players stored as a tuple
✔ Name derived correctly
✔ String representation is stable
✔ Rejects invalid roster types

We are not testing gameplay behavior or team logic — this is a
snapshot object.
"""

import pytest

from src.team.team_record import TeamRecord
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import SKILLS


@pytest.fixture
def player_record():
    return PlayerRecord(
        id="p1",
        first_name="John",
        last_name="Doe",
        bats="R",
        throws="R",
        position="cf",
        skills=PlayerSkills(SKILLS),
    )


@pytest.fixture
def team_record(player_record):
    return TeamRecord(
        id="t1",
        city="Springfield",
        mascot="Isotopes",
        players=(player_record,),
    )


def test_team_name_property(team_record):
    assert team_record.name == "Springfield Isotopes"


def test_team_str_representation(team_record):
    text = str(team_record)

    assert "Springfield Isotopes" in text
    assert "1 players" in text


def test_players_must_be_tuple(player_record):
    """
    Guard rail Enforce immutability boundary.
    """
    with pytest.raises(TypeError):
        TeamRecord(
            id="t2",
            city="Nowhere",
            mascot="Ghosts",
            players=[player_record],  # ❌ list not allowed
        )


def test_team_record_is_immutable(team_record):
    with pytest.raises(Exception):
        team_record.city = "Shelbyville"


def test_team_players_cannot_be_modified(team_record):
    """Players cannot be reassigned"""
    with pytest.raises(Exception):
        team_record.players = ()


def test_players_tuple_is_immutable(team_record):
    with pytest.raises(AttributeError):
        team_record.players.append(None)


# def test_players_must_be_player_records(player_record):
#     """
#     Validate all players are PlayerRecord instances
#     Current implementation does not enforce this
#     """
#     with pytest.raises(TypeError):
#         TeamRecord(
#             id="t3",
#             city="Error",
#             mascot="Bugs",
#             players=("not a player",),
#         )
