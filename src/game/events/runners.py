# src/game/events/bases.py
"""
RunnerAdvancedEvent is the only place
where “runner reaches home” is interpreted.

Resolver says what happened
Bases enforces movement
RunnerAdvancedEvent converts to_base == 4 → score

RunnerAdvancedEvent reason meanings:

    "force":
        - Movement was mandatory
        - No RNG involved
        - Runner had no legal alternative

    Other reasons ("single", "double", etc.):
        - Movement was decided by resolver logic
        - May involve RNG, heuristics, or player attributes
"""
from dataclasses import dataclass
import logging
from typing import Optional

from src.game.event import GameEvent
from src.game.events.scoring import RunScoredEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class RunnerAdvancedEvent(GameEvent):
    """
    A runner advances from one base to another.

    from_base:
        None → runner came from batter's box
    to_base:
        1, 2, 3, or 4 (4 = home)
        Treat anything over 4 as home
    """

    runner: PlayerInGame
    pitcher: PlayerInGame
    from_base: Optional[int]
    to_base: int
    reason: Optional[str] = None
    rbi_batter: PlayerInGame | None = None

    def apply(self, game) -> list[GameEvent]:
        game.bases.advance(
            runner=self.runner,
            from_base=self.from_base,
            to_base=self.to_base,
        )

        if self.to_base >= 4:
            return [
                RunScoredEvent(
                    runner=self.runner,
                    rbi_batter=self.rbi_batter,
                    reason=self.reason or "run",
                    pitcher=self.pitcher,
                )
            ]

        return []

    def log_level(self) -> int:
        return logging.DEBUG

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Runner(s) advanced. {game.bases}"


@dataclass(frozen=True)
class RunnerRemovedEvent(GameEvent):
    """
    A runner is removed from the bases (out or scored).
    """

    runner: PlayerInGame
    from_base: Optional[int]
    reason: Optional[str] = None

    def apply(self, game):
        game.bases.remove(
            runner=self.runner,
            from_base=self.from_base,
        )

    def log_level(self) -> int:
        return logging.DEBUG
