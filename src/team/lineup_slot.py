from dataclasses import dataclass

from src.player.player_in_game import PlayerInGame

LINEUP_SLOTS = [
    "cf",
    "ss",
    "2b",
    "1b",
    "lf",
    "3b",
    "rf",
    "c",
]
POSITION_PRIORITY = ["ss", "cf", "2b", "c", "3b", "rf", "1b", "lf"]


@dataclass(slots=True)
class LineupSlot:
    player: PlayerInGame
    position: str
