# src/game/events/hbp.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class HitByPitchEvent(GameEvent):
    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.hit_batter()
        self.pitcher.game_stats.pitching.hit_batter()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was hit by pitch."
