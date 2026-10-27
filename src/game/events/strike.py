# src/game/events/strike.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class StrikeEvent(GameEvent):
    """
    Simply adds a strike to the count.
    """

    swinging: bool = False

    def apply(self, game):
        game.count.add_strike()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        kind = "Swinging" if self.swinging else "Called"
        return f"{kind} strike {game.count.strikes}"


@dataclass(frozen=True)
class FoulStrikeEvent(GameEvent):
    """
    Simply adds a strike to the count.

    This cannot occur with 2 strikes.
    """

    swinging: bool = True

    def apply(self, game):
        game.count.add_strike()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Foul ball, strike {game.count.strikes}"


@dataclass(frozen=True)
class FouledOffThirdStrikeEvent(GameEvent):
    """
    This is merely for logging, there is no change to the count.
    """

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Foul ball, remains strike {game.count.strikes}"


@dataclass(frozen=True)
class FoulTipCaughtThirdStrikeEvent(GameEvent):
    """
    This is a foul tip that is caught.
    A StrikeoutEvent should be called any time this is called.
    """

    def apply(self, game):
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Foul ball tipped and caught"
