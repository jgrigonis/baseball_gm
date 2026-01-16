# src/game/events/strikeout.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class StrikeOutEvent(GameEvent):
    swinging: bool = False

    def apply(self, game):
        pass  # this does nothing
        # game.inning.record_out()
        # game._mark_plate_appearance_complete("strikeout")
