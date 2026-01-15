# src/game/events/strike.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class StrikeEvent(GameEvent):
    swinging: bool = False

    def apply(self, game):
        game.count.add_strike()
