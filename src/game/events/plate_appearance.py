# src/game/events/plate_appearance.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class PlateAppearanceEndEvent(GameEvent):
    """
    Marks the end of the current plate appearance.
    This is the ONLY way a PA may end.

    This is the ONLY event allowed to end a plate appearance.
    Game logic must react to it via _post_event().

    PlateAppearanceEndEvent must be the last event of the plate appearance.
    Nothing that mutates PA state may occur after it.
    """

    reason: str
    batter: PlayerInGame

    def apply(self, game):
        game._mark_plate_appearance_complete(self.reason)
        self.batter.game_stats.batting.plate_appearance()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.bases}"

    def should_log(self, game) -> bool:
        """
        We don't need to print bases at the end of the inning,
        and it's often wrong.
        """
        if game.inning.outs >= 3:
            return False
        else:
            return True
