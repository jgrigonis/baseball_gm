# src/game/intents/pitch.py
from dataclasses import dataclass
from typing import Optional

from src.game.intent import GameIntent


@dataclass(frozen=True)
class PitchIntent(GameIntent):
    pitcher_id: str
    batter_id: str

    # Optional advisory info (AI / UI)
    pitch_type: Optional[str] = None
    target: Optional[str] = None
