# src/game/events/hbp.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class HitByPitchEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass
        # base advance handled in _resolve_walk
        # game.bases.advance(game.current_batter, None, 1)

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} was hit by pitch."
