# src/game/events/out.py
from dataclasses import dataclass
from typing import Optional

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class OutRecordedEvent(GameEvent):
    """
    Records an out in the game and as a pitcher stat.
    """

    reason: str
    pitcher: PlayerInGame

    def apply(self, game):
        game.inning.record_out()
        self.pitcher.game_stats.pitching.out()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        if game.inning.outs == 1:
            return "1 out"
        else:
            return f"{game.inning.outs} outs"


@dataclass(frozen=True)
class GroundOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} grounded out."


@dataclass(frozen=True)
class FlyOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a fly out."


@dataclass(frozen=True)
class FoulFlyOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    batter: PlayerInGame

    def apply(self, game):
        self.batter.game_stats.batting.at_bat()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.batter.name} hit a foul fly out."


@dataclass(frozen=True)
class PutOutEvent(GameEvent):
    """
    Simply adds an at bat to the batter
    """

    fielder: PlayerInGame
    assist: Optional[PlayerInGame] = None

    def apply(self, game):
        self.fielder.game_stats.fielding.putout()
        if self.assist:
            self.assist.game_stats.fielding.assist()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        msg = f"{self.fielder.name} ({self.fielder.current_position}) with the putout."
        if self.assist:
            msg += f" {self.assist.name} ({self.assist.current_position}) with the assist"
        return msg
