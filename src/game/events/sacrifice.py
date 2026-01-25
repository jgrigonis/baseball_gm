# src/game/events/sacrifice.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class SacBuntEvent(GameEvent):
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.sac_bunt()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} laid down a sacrifice bunt."


@dataclass(frozen=True)
class SacFlyEvent(GameEvent):
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.sac_fly()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a sacrifice fly."
