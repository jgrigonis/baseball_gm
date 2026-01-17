# src/tests/game/test_queue.py
from tests.utils import fake_game, real_game
from src.game.game import GameEvent


def test_enqueueleft_preserves_order():
    game = real_game()

    applied = []

    class EventA(GameEvent):
        def apply(self, game):
            applied.append("A")

    class EventB(GameEvent):
        def apply(self, game):
            applied.append("B")

    game._enqueueleft([EventA(), EventB()])

    game.step()
    game.step()

    assert applied == ["A", "B"]


def test_enqueue_extends_to_back():
    game = real_game()

    applied = []

    class EventA(GameEvent):
        def apply(self, game):
            applied.append("A")

    class EventB(GameEvent):
        def apply(self, game):
            applied.append("B")

    game._enqueue([EventA(), EventB()])

    game.step()
    game.step()

    assert applied == ["A", "B"]
