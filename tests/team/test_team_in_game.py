# tests/team/test_team_in_game.py
"""
What we test (and don't)
We DO test

Player wrapping (PlayerRecord → PlayerInGame)
Initial state
Lineup lifecycle
Batter iteration logic
Error behavior before lineup is set
Pitcher assignment passthrough

We DO NOT test

Lineup optimization correctness
Player evaluation math
Strategy quality
Those belong to other test files.
"""

import pytest
from unittest.mock import MagicMock

from src.team.team_in_game import TeamInGame
from src.team.team_record import TeamRecord
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.player_in_game import PlayerInGame
from src.team.lineup_slot import LineupSlot
from src.player.positions import SKILLS


def full_skills(value=50):
    return PlayerSkills.from_row({k: value for k in SKILLS})


@pytest.fixture
def player_record():
    return PlayerRecord(
        id="p1",
        first_name="John",
        last_name="Doe",
        bats="right",
        throws="right",
        skills=full_skills(),
    )


@pytest.fixture
def team_record(player_record):
    return TeamRecord(
        id="t1",
        city="Springfield",
        mascot="Isotopes",
        players=(player_record,),
    )


@pytest.fixture
def team_in_game(team_record):
    return TeamInGame(team_record)


def test_team_in_game_initial_state(team_in_game):
    assert team_in_game.players
    assert isinstance(team_in_game.players[0], PlayerInGame)

    assert team_in_game.lineup == []
    assert team_in_game.pitcher is None
    assert team_in_game.batter_index == 0


def test_players_wrapped_from_record(team_record):
    """PlayerRecords are wrapped, not mutated"""
    tig = TeamInGame(team_record)

    assert len(tig.players) == len(team_record.players)
    assert tig.players[0].record is team_record.players[0]


def test_current_batter_raises_if_lineup_not_set(team_in_game):
    """Cannot access batter before lineup is set"""
    with pytest.raises(RuntimeError):
        team_in_game.current_batter()


def test_set_lineup_assigns_lineup_and_pitcher(team_in_game):
    """
    set_lineup() delegates to the injected optimizer
    """
    fake_batter = MagicMock(spec=LineupSlot)
    fake_pitcher = MagicMock(spec=PlayerInGame)

    mock_optimize = MagicMock(return_value=([fake_batter], fake_pitcher))
    team_in_game._optimizer = mock_optimize

    team_in_game.set_lineup()

    assert team_in_game.lineup == [fake_batter]
    assert team_in_game.pitcher is fake_pitcher
    assert team_in_game.batter_index == 0

    mock_optimize.assert_called_once_with(
        team_in_game.players,
        style="prioritized",
        dh=True,
    )


def test_next_batter_cycles():
    """Batter iteration wraps correctly

    Using __new__ avoids needing full setup — intentional for tight
    unit tests.
    """
    tig = TeamInGame.__new__(TeamInGame)

    tig.lineup = ["a", "b", "c"]
    tig.batter_index = 0

    assert tig.current_batter() == "a"
    assert tig.next_batter() == "b"
    assert tig.next_batter() == "c"
    assert tig.next_batter() == "a"  # wrap


def test_current_pitcher_returns_pitcher(team_in_game):
    """current_pitcher() passthrough"""
    pitcher = MagicMock(spec=PlayerInGame)
    team_in_game.pitcher = pitcher

    assert team_in_game.current_pitcher() is pitcher


def test_set_lineup_rates_unrated_players(team_in_game):
    mock_optimize = MagicMock(return_value=([], None))
    team_in_game._optimizer = mock_optimize

    for p in team_in_game.players:
        if hasattr(p, "ratings"):
            del p.ratings
        p.rate_player = MagicMock()

    team_in_game.set_lineup()

    for p in team_in_game.players:
        p.rate_player.assert_called_once()

    mock_optimize.assert_called_once()
