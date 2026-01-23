# src/game/events/double_play.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class DoublePlayEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        # game.inning.record_out()
        pass  # outs are applied elsewhere

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit into a double play."
