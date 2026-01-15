# tests/test_inning.py
import pytest

from src.game.game import Game
from tests.utils import FakeRNG, FakeTeam

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


def test_three_outs_end_half_inning(game):
    game.inning.outs = 3
    assert game._half_inning_over()


def test_half_inning_reset_clears_bases_and_count(game):
    game.inning.outs = 3
    # print(game.bases._bases)
    game.bases.advance(runner_id="p1", from_base=None, to_base=1)
    # print(game.bases._bases)
    game.count.balls = 2
    assert game.bases.occupied_bases() == {1: "p1"}
    game._end_half_inning()

    assert game.bases.occupied_bases() == {}
    assert game.count.balls == 0
