# src/game/events/ball.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class BallEvent(GameEvent):
    """
    This event simply increments the balls. If it increments to 4
    balls, that is dealt with elsewhere.
    """

    def apply(self, game):
        game.count.add_ball()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Ball {game.count.balls}"


@dataclass(frozen=True)
class IllegalPitch(GameEvent):
    """
    This is used for things like a quick pitch, or illegal windup.

    They should be fairly rare, but they result in a ball being
    awarded to the batter. If runners are on base, these illegal
    actions are treated as a balk.

    Any time an illegal pitch is called, a ball event should be
    executed as well.
    """

    pitcher: PlayerInGame

    def apply(self, game):
        self.pitcher.game_stats.pitching.illegal_pitch()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Illegal pitch!"
