import pytest
from unittest.mock import Mock

from tests.utils import FakeTeam, FakeRNG
from src.game.game import Game


@pytest.fixture
def home_team():
    return FakeTeam(name="Home")


@pytest.fixture
def away_team():
    return FakeTeam(name="Away")


@pytest.fixture
def game(home_team, away_team):
    game = Game(
        home_team=home_team,
        away_team=away_team,
        rng=FakeRNG([0.5] * 100),
    )
    game._sync_players()
    return game


@pytest.fixture
def game_no_rng(home_team, away_team):
    game = Game(
        home_team=home_team,
        away_team=away_team,
    )
    game._sync_players()
    return game


@pytest.fixture
def mock_teams():
    """Create mock teams for testing."""
    home = Mock()
    home.record = Mock()
    home.record.id = "home-123"
    home.record.city = "Home"
    home.record.mascot = "Team"
    home.name = "Home Team"
    home.has_lineup = True
    home.players = []

    away = Mock()
    away.record = Mock()
    away.record.id = "away-456"
    away.record.city = "Away"
    away.record.mascot = "Team"
    away.name = "Away Team"
    away.has_lineup = True
    away.players = []

    return home, away


# This is not accurate
# @pytest.fixture
# def game_with_loaded_bases(game):
#     game.bases.load([1, 2]) # WRONG
#     return game
