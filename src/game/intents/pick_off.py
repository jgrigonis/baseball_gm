# src/game/intents/pick_off.py
from dataclasses import dataclass

from src.game.intent import GameIntent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class PickOffIntent(GameIntent):
    pitcher: PlayerInGame
    target_base: str
