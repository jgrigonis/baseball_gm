from dataclasses import dataclass

from src.player.player_in_game import PlayerInGame


@dataclass(slots=True)
class LineupSlot:
    player: PlayerInGame
    position: str
