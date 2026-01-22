# src/game/events/fielder_choice.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class FieldersChoiceEvent(GameEvent):
    batter_id: str

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_batter.player.name} hit into a fielder's choice."
