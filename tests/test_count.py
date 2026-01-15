# src/tests/test_count.py
import pytest

from src.game.game import Game
from tests.utils import FakeRNG, FakeTeam
from src.game.events.strike import StrikeEvent
from src.game.events.ball import BallEvent


# @pytest.fixture
# def fake_team():
#     return FakeTeam()



# @pytest.fixture
# def game(fake_team):
#     game = Game(
#         home_team=fake_team,
#         away_team=fake_team,
#         rng=FakeRNG([0.5] * 100),
#     )
#     game._sync_players()
#     return game

def test_ball_increments_balls(game):
    BallEvent().apply(game)
    assert game.count.balls == 1


def test_strike_increments_strikes(game):
    StrikeEvent().apply(game)
    assert game.count.strikes == 1

