# src/game/events/walk.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class WalkEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass
        # base advance handled in _resolve_walk

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} was issued a walk."


@dataclass(frozen=True)
class IBBEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} was issued an intentional walk."


@dataclass(frozen=True)
class CatcherInterferenceEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} was issued first base for catcher interference."
