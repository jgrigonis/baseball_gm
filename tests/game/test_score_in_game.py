# tests/test_score.py
from tests.utils import fake_game

from src.game.events.scoring import RunScoredEvent
from src.player.player_in_game import PlayerInGame
from tests.factories.player_record_factory import make_player_record


def test_score_uses_inning_state():
    game = fake_game()
    game.inning.number = 3
    game.inning.top = False

    RunScoredEvent(
        runner=PlayerInGame(make_player_record()),
        rbi_batter=PlayerInGame(make_player_record()),
        reason="test",
        pitcher=PlayerInGame(make_player_record()),
    ).apply(game)

    assert game.score.home == 1
    assert game.score.away == 0
