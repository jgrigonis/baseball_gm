# src/game/events/strikeout.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class StrikeOutEvent(GameEvent):
    swinging: bool = False

    def apply(self, game):
        pass  # this does nothing

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Strikeout"
