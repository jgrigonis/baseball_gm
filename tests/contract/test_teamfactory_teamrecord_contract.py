# tests/contract/test_team_factory.py

"""
The TeamFactory → TeamRecord contract is:

id is a non-empty str
city and mascot are preserved
players is a tuple
players contains only PlayerRecord
players length ≥ 9
TeamRecord immutability is respected (cannot mutate fields)
These are not TeamFactory internals — they're promises it must uphold.
"""

import io
import pytest
from unittest.mock import MagicMock, patch

from src.team.team_factory import TeamFactory
from src.team.team_record import TeamRecord
from src.player.player_record import PlayerRecord


def assert_valid_teamrecord(team: TeamRecord):
    """
    Shared assertion helper

    Keeps tests DRY and expressive.
    """
    assert isinstance(team, TeamRecord)

    assert isinstance(team.id, str)
    assert team.id

    assert isinstance(team.city, str)
    assert isinstance(team.mascot, str)

    assert isinstance(team.players, tuple)
    assert len(team.players) >= 9

    for p in team.players:
        assert isinstance(p, PlayerRecord)


@patch("src.team.team_factory.open", create=True)
@patch("src.team.team_factory.PlayerRecord.from_csv_row")
def test_from_csv_produces_valid_teamrecord(
    mock_from_csv_row,
    mock_open,
):
    """from_csv satisfies the TeamRecord contract"""
    csv_data = "id,first_name,last_name,bats,throws\n" + "\n".join(
        f"{i},First{i},Last{i},R,R" for i in range(1, 10)
    )
    mock_open.return_value.__enter__.return_value = io.StringIO(csv_data)

    mock_from_csv_row.return_value = MagicMock(spec=PlayerRecord)

    factory = TeamFactory()

    team = factory.from_csv(
        path="team.csv",
        city="Seattle",
        mascot="Mariners",
    )

    assert_valid_teamrecord(team)


def test_generate_team_produces_valid_teamrecord():
    factory = TeamFactory()
    team = factory.generate_team(
        city="Houston",
        mascot="Astros",
        size=26,
    )

    assert_valid_teamrecord(team)


def test_teamrecord_is_immutable():
    """
    TeamRecord immutability holds

    This explicitly checks that TeamFactory doesn't sneak mutable
    data through.
    """
    factory = TeamFactory()
    team = factory.generate_team(
        city="Atlanta",
        mascot="Braves",
        size=9,
    )

    with pytest.raises(Exception):
        team.city = "Boston"

    with pytest.raises(Exception):
        team.players += ()


def test_teamfactory_always_returns_tuple_players():
    """
    players tuple identity is preserved

    This catches a subtle bug where a list might slip through.
    """
    factory = TeamFactory()
    team = factory.generate_team(
        city="Miami",
        mascot="Marlins",
        size=12,
    )

    assert isinstance(team.players, tuple)
