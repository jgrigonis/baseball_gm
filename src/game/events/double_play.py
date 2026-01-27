# src/game/events/double_play.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class DoublePlayEvent(GameEvent):
    """
    Executes a double play event.
    Add the stats to the batter, the outs are recorded elsewhere.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.ground_double_play()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.ground_double_play()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit into a double play."
