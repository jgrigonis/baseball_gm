# tests/team/test_team_factory.py
"""
What we want to test
from_csv
Reads rows and delegates to PlayerRecord.from_row
Raises a row-numbered error on invalid player data
Requires at least 9 players
Produces a valid, immutable TeamRecord

generate_team
Uses PlayerFactory.create
Produces the requested roster size
"""

import io
import pytest
from unittest.mock import MagicMock, patch

from src.team.team_factory import TeamFactory
from src.team.team_record import TeamRecord
from src.player.player_record import PlayerRecord


@pytest.fixture
def valid_csv():
    header = "id,first_name,last_name,bats,throws\n"
    rows = [f"{i},First{i},Last{i},R,R\n" for i in range(1, 10)]
    return header + "".join(rows)


@patch("src.team.team_factory.open", create=True)
@patch("src.team.team_factory.PlayerRecord.from_csv_row")
def test_from_csv_creates_team_record(
    mock_from_csv_row,
    mock_open,
    valid_csv,
):
    """Happy path: builds a TeamRecord"""
    mock_open.return_value.__enter__.return_value = io.StringIO(valid_csv)

    fake_player = MagicMock(spec=PlayerRecord)
    mock_from_csv_row.return_value = fake_player

    factory = TeamFactory()

    team = factory.from_csv(
        path="team.csv",
        city="Chicago",
        mascot="Bears",
    )

    assert isinstance(team, TeamRecord)
    assert team.city == "Chicago"
    assert team.mascot == "Bears"
    assert len(team.players) == 9
    assert all(p is fake_player for p in team.players)


@patch("src.team.team_factory.open", create=True)
@patch("src.team.team_factory.PlayerRecord.from_csv_row")
def test_from_csv_invalid_row_reports_row_number(
    mock_from_csv_row,
    mock_open,
    valid_csv,
):
    """Invalid row includes row number in error"""
    mock_open.return_value.__enter__.return_value = io.StringIO(valid_csv)

    mock_from_csv_row.side_effect = ValueError("bad data")

    factory = TeamFactory()

    with pytest.raises(ValueError, match="Invalid player row 1"):
        factory.from_csv(
            path="team.csv",
            city="NY",
            mascot="Mets",
        )


@patch("src.team.team_factory.open", create=True)
@patch("src.team.team_factory.PlayerRecord.from_csv_row")
def test_from_csv_requires_minimum_players(
    mock_from_csv_row,
    mock_open,
):
    """Fewer than 9 players is rejected"""
    csv_data = "ID,Name,B,T\n" "1,A,R,R\n" "2,C,R,R\n"
    mock_open.return_value.__enter__.return_value = io.StringIO(csv_data)
    mock_from_csv_row.return_value = MagicMock(spec=PlayerRecord)

    factory = TeamFactory()

    with pytest.raises(ValueError, match="at least 9 players"):
        factory.from_csv(
            path="small.csv",
            city="LA",
            mascot="Dodgers",
        )


def test_generate_team_creates_requested_size():
    factory = TeamFactory()
    factory.player_factory.create = MagicMock()

    fake_player = MagicMock(spec=PlayerRecord)
    factory.player_factory.create.return_value = fake_player

    team = factory.generate_team(
        city="Boston",
        mascot="Red Sox",
        size=15,
    )

    assert isinstance(team, TeamRecord)
    assert len(team.players) == 15
    factory.player_factory.create.assert_called()


def test_generate_team_players_are_tuple():
    factory = TeamFactory()
    factory.player_factory.create = MagicMock(return_value=MagicMock(spec=PlayerRecord))

    team = factory.generate_team(
        city="SF",
        mascot="Giants",
        size=9,
    )

    assert isinstance(team.players, tuple)
