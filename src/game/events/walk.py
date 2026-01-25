# src/game/events/walk.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class WalkEvent(GameEvent):
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
    batter: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        # TODO track intentional walks separate
        self.batter.game_stats.batting.walk()
        self.pitcher.game_stats.pitching.walk()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was issued an intentional walk."


@dataclass(frozen=True)
class CatcherInterferenceEvent(GameEvent):
    batter: PlayerInGame
    pitcher: PlayerInGame
    catcher: PlayerInGame

    def apply(self, game):
        # TODO track catcher interference separately
        # And add catcher stat
        self.batter.game_stats.batting.walk()
        self.pitcher.game_stats.pitching.walk()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} was issued first base for catcher interference."
