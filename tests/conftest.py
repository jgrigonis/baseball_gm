import pytest

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

# @pytest.fixture
# def game_with_loaded_bases(game):
#     game.bases.load([1, 2]) # WRONG
#     return game

