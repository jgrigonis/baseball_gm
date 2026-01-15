# src/game/events/noop.py
from __future__ import annotations

from dataclasses import dataclass
from src.game.event import GameEvent

@dataclass
class NoOpEvent(GameEvent):
    def apply(self, game):
        pass
