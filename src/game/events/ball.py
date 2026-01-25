# src/game/events/ball.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class BallEvent(GameEvent):
    def apply(self, game):
        game.count.add_ball()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Ball {game.count.balls}"


@dataclass(frozen=True)
class IllegalPitch(GameEvent):
    pitcher: PlayerInGame

    def apply(self, game):
        self.pitcher.game_stats.pitching.illegal_pitch()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Illegal pitch!"
