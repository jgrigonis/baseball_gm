# src/game/events/walk.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class WalkEvent(GameEvent):
    def apply(self, game):
        game.bases.advance(game.current_batter, None, 1)
