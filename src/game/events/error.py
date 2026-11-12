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
        game._inning_had_error = True

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} got on base via a fielding error by {self.fielder.name} ({self.fielder.current_position})."


@dataclass
class ThrowingErrorEvent(GameEvent):
    fielder: PlayerInGame
    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()
        self.fielder.game_stats.fielding.error()
        game._inning_had_error = True

    def describe(self, game) -> str:
        return f"{self.batter.name} reached base on a throwing error by {self.fielder.name} ({self.fielder.current_position})."


@dataclass
class OutfielderThrowingErrorEvent(GameEvent):
    """Outfielder throws badly, runner advances an extra base."""

    fielder: PlayerInGame
    runner: PlayerInGame

    def apply(self, game):
        self.fielder.game_stats.fielding.error()
        game._inning_had_error = True

    def describe(self, game) -> str:
        return (
            f"{self.runner.name} advanced on a throwing error by {self.fielder.name}."
        )


@dataclass
class RunnerAdvancedOnErrorEvent(GameEvent):
    """A runner takes an extra base because a fielder threw or dropped the ball."""

    fielder: PlayerInGame
    runner: PlayerInGame
    kind: str = "throwing"  # "throwing" or "fielding"

    def apply(self, game):
        self.fielder.game_stats.fielding.error()
        game._inning_had_error = True

    def describe(self, game) -> str:
        return (
            f"{self.runner.name} took an extra base on a {self.kind} error by "
            f"{self.fielder.name} ({self.fielder.current_position})."
        )


@dataclass
class ErrorChargedEvent(GameEvent):
    """An error on a play whose other events already did the batter's
    bookkeeping (a dropped third strike thrown away: the strikeout counted
    his at bat)."""

    fielder: PlayerInGame

    def apply(self, game):
        self.fielder.game_stats.fielding.error()
        game._inning_had_error = True

    def describe(self, game) -> str:
        return f"Error on {self.fielder.name} ({self.fielder.current_position})."
