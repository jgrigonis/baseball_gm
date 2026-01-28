# src/game/events/walk.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class WalkEvent(GameEvent):
    """
    Apply walk stats to pitcher and batter.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.walk()
        self.pitcher.game_stats.pitching.walk()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was issued a walk."


@dataclass(frozen=True)
class IBBEvent(GameEvent):
    """
    Apply walk stats to pitcher and batter.
    Also applies intentional walk stats.
    """

    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.intentional_walk()
        self.batter.game_stats.batting.walk()
        self.pitcher.game_stats.pitching.walk()
        self.pitcher.game_stats.pitching.intentional_walk()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was issued an intentional walk."


@dataclass(frozen=True)
class CatcherInterferenceEvent(GameEvent):
    """
    This only counts as a catcher_interference on the catcher
    The base is awarded to the batter elsewhere.
    It also counts as an error but that is handled in
    catcher_interference()
    """

    batter: PlayerInGame
    pitcher: PlayerInGame
    catcher: PlayerInGame

    def apply(self, game):
        self.catcher.game_stats.fielding.catcher_interference()
        self.batter.game_stats.batting.catcher_interference()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was issued first base for catcher interference."
