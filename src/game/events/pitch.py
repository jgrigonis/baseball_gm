# src/game/events/pitch.py
from dataclasses import dataclass
from typing import Optional

from src.game.count import CountSnapshot
from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class PitchThrownEvent(GameEvent):
    """
    A pitch has been thrown.
    This is observational only.
    It does add to the pitch count.
    """

    pitcher: PlayerInGame
    batter: PlayerInGame
    count: CountSnapshot
    pitch_type: Optional[str] = None  # fastball, curve, etc. (optional for now)

    def apply(self, game):
        game.logger.trace("PitchThrownEvent applied")
        self.pitcher.game_stats.pitching.pitch()

    def should_log(self, game) -> bool:
        """We don't need to log every pitch."""
        return False
