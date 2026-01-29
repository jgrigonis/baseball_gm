# src/game/events/noop.py
from __future__ import annotations

from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class NoOpEvent(GameEvent):
    def apply(self, game):
        pass
