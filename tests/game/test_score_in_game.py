# tests/test_score.py
from tests.utils import fake_game

from src.game.events.scoring import RunScoredEvent


def test_score_uses_inning_state():
    game = fake_game()
    game.inning.number = 3
    game.inning.top = False

    RunScoredEvent("r1", None, "test").apply(game)

    assert game.score.home == 1
    assert game.score.away == 0
