# src/game/events/hits.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class SingleEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass
        # base advance handled in _resolve_walk

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit a single."


@dataclass(frozen=True)
class HomeRunEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass
        # base advance handled in _resolve_walk

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit a home run."
