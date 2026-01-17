# src/game/events/pitch.py
from dataclasses import dataclass
from typing import Optional

from src.game.count import CountSnapshot
from src.game.event import GameEvent


@dataclass(frozen=True)
class PitchThrownEvent(GameEvent):
    """
    A pitch has been thrown.
    This is observational only.
    """

    pitcher_id: str
    batter_id: str
    count: CountSnapshot
    pitch_type: Optional[str] = None  # fastball, curve, etc. (optional for now)

    def apply(self, game):
        game.logger.trace("PitchThrownEvent applied")
