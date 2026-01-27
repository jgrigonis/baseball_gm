# src/game/events/hits.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class SingleEvent(GameEvent):
    """
    Single Event. This simply applies stats to pitcher and batter.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.hit()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.hit()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a single."


@dataclass(frozen=True)
class DoubleEvent(GameEvent):
    """
    This simply applies stats to pitcher and batter.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.hit()
        self.batter.game_stats.batting.double()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.hit()
        self.pitcher.game_stats.pitching.double()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a double."


@dataclass(frozen=True)
class TripleEvent(GameEvent):
    """
    This simply applies stats to pitcher and batter.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.hit()
        self.batter.game_stats.batting.triple()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.hit()
        self.pitcher.game_stats.pitching.triple()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a triple."


@dataclass(frozen=True)
class HomeRunEvent(GameEvent):
    """
    This simply applies stats to pitcher and batter.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.hit()
        self.batter.game_stats.batting.home_run()
        self.batter.game_stats.batting.at_bat()
        self.pitcher.game_stats.pitching.hit()
        self.pitcher.game_stats.pitching.home_run()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a home run."
