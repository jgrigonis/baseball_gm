# src/game/events/plate_appearance.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class PlateAppearanceEndEvent(GameEvent):
    """
    Marks the end of the current plate appearance.
    This is the ONLY way a PA may end.

    This is the ONLY event allowed to end a plate appearance.
    Game logic must react to it via _post_event().

    """

    reason: str

    def apply(self, game):
        game._mark_plate_appearance_complete(self.reason)
