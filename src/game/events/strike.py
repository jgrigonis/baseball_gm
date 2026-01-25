# src/game/events/strike.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class StrikeEvent(GameEvent):
    swinging: bool = False

    def apply(self, game):
        game.count.add_strike()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Strike {game.count.strikes}"


@dataclass(frozen=True)
class FoulStrikeEvent(GameEvent):
    swinging: bool = True

    def apply(self, game):
        game.count.add_strike()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Foul ball, strike {game.count.strikes}"


@dataclass(frozen=True)
class FouledOffThirdStrikeEvent(GameEvent):
    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Foul ball, remains strike {game.count.strikes}"


@dataclass(frozen=True)
class FoulTipCaughtThirdStrikeEvent(GameEvent):
    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Foul ball tipped and caught"
