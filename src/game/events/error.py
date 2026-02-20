# In src/game/events/error.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass
class FieldingErrorEvent(GameEvent):
    fielder: PlayerInGame
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()
        self.fielder.game_stats.fielding.error()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} got on base via an error."


@dataclass
class ThrowingErrorEvent(GameEvent):
    fielder: PlayerInGame
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()
        self.fielder.game_stats.fielding.error()

    def describe(self, game) -> str:
        return f"{self.batter.name} reached base on a throwing error by {self.fielder.name}."


@dataclass
class OutfielderThrowingErrorEvent(GameEvent):
    """Outfielder throws badly, runner advances an extra base."""

    fielder: PlayerInGame
    runner: PlayerInGame

    def apply(self, game):
        self.fielder.game_stats.fielding.error()

    def describe(self, game) -> str:
        return (
            f"{self.runner.name} advanced on a throwing error by {self.fielder.name}."
        )
