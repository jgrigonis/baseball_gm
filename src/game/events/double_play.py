# src/game/events/double_play.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class DoublePlayEvent(GameEvent):
    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.ground_double_play()
        self.batter.game_stats.batting.at_bat()
        # pitcher stat
        pass  # outs are applied elsewhere

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit into a double play."
