# src/game/intents/pick_off.py
from dataclasses import dataclass

from src.game.intent import GameIntent


@dataclass(frozen=True)
class PickOffIntent(GameIntent):
    pitcher_id: str
    target_base: str
