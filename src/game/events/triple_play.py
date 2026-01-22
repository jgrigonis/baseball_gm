# src/game/events/triple_play.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class TriplePlayEvent(GameEvent):
    reason: str

    def apply(self, game):
        # game.inning.record_out()
        pass  # outs are applied elsewhere

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit into a triple play!"
