# src/game/events/triple_play.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class TriplePlayEvent(GameEvent):
    """
    Adds a triple play stat for the batter and an atbat.
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.ground_triple_play()
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit into a triple play!"
