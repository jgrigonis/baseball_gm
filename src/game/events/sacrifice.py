# src/game/events/sacrifice.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class SacBuntEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} laid down a sacrifice bunt."

@dataclass(frozen=True)
class SacFlyEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit a sacrifice fly."
