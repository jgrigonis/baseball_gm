# src/game/events/hbp.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class HitByPitchEvent(GameEvent):
    def apply(self, game):
        game.bases.advance(game.current_batter, None, 1)
