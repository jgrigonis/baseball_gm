# src/game/events/out.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class OutRecordedEvent(GameEvent):
    reason: str

    def apply(self, game):
        game.inning.record_out()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        if game.inning.outs == 1:
            return "1 out"
        else:
            return f"{game.inning.outs} outs"
