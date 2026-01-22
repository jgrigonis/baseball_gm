# src/game/events/ball.py
from dataclasses import dataclass
from src.game.event import GameEvent


@dataclass(frozen=True)
class BallEvent(GameEvent):
    def apply(self, game):
        game.count.add_ball()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Ball {game.count.balls}"


@dataclass(frozen=True)
class IllegalPitch(GameEvent):
    def apply(self, game):
        pass  # ball is added separately

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Illegal pitch!"
