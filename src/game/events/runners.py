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

from src.game.event import GameEvent
from src.game.events.scoring import RunScoredEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class ReachedBaseEvent(GameEvent):
    runner: PlayerInGame
    base: int
    reason: str  # "single", "double", "walk", "hit_by_pitch", "fielders_choice", "error", etc.
    responsible_pitcher: PlayerInGame | None

    def apply(self, game):
        self.runner.responsible_pitcher = self.responsible_pitcher
        self.runner.ghost_runner = False  # he reached on his own this time

    def log_level(self) -> int:
        return logging.DEBUG

    def describe(self, game) -> str:
        return f"{self.runner.name} reached {self.base} on {self.reason}."


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
    from_base: int | None
    to_base: int
    reason: str | None = None
    rbi_batter: PlayerInGame | None = None

    def apply(self, game) -> list[GameEvent]:
        game.bases.advance(
            runner=self.runner,
            from_base=self.from_base,
            to_base=self.to_base,
        )

        if self.to_base >= 4:
            # A batter who comes all the way around (a home run) is the
            # pitcher's own run. Don't read runner.responsible_pitcher for
            # him: it's left over from his last time on base, maybe off a
            # pitcher who has since left the game.
            responsible = (
                self.pitcher
                if self.from_base is None
                else getattr(self.runner, "responsible_pitcher", None) or self.pitcher
            )
            # The extra-innings runner placed on second scores unearned.
            ghost = self.from_base is not None and getattr(
                self.runner, "ghost_runner", False
            )
            if ghost:
                self.runner.ghost_runner = False
            return [
                RunScoredEvent(
                    runner=self.runner,
                    rbi_batter=self.rbi_batter,
                    reason=self.reason or "run",
                    pitcher=self.pitcher,
                    responsible_pitcher=responsible,
                    earned=not ghost,
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
    from_base: int | None
    reason: str | None = None

    def apply(self, game):
        game.bases.remove(
            runner=self.runner,
            from_base=self.from_base,
        )

    def log_level(self) -> int:
        return logging.DEBUG
