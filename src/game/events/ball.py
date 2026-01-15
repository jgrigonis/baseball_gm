# src/game/events/ball.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class BallEvent(GameEvent):
    def apply(self, game):
        game.count.add_ball()
