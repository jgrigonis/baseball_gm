# src/game/events/strikeout.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class StrikeOutEvent(GameEvent):
    batter: PlayerInGame
    pitcher: PlayerInGame
    swinging: bool = False

    def apply(self, game):
        self.batter.game_stats.batting.strike_out()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.strike_out()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Strikeout"
