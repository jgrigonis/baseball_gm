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
from typing import Optional

from src.game.event import GameEvent
from src.game.events.scoring import RunScoredEvent


@dataclass(frozen=True)
class RunnerAdvancedEvent(GameEvent):
    """
    A runner advances from one base to another.

    from_base:
        None → runner came from batter's box
    to_base:
        1, 2, 3, or 4 (4 = home)
    """

    runner_id: str
    from_base: Optional[int]
    to_base: int
    reason: Optional[str] = None
    rbi_batter_id: str | None = None

    def apply(self, game) -> list[GameEvent]:
        game.bases.advance(
            runner_id=self.runner_id,
            from_base=self.from_base,
            to_base=self.to_base,
        )

        if self.to_base == 4:
            return [
                RunScoredEvent(
                    runner_id=self.runner_id,
                    rbi_batter_id=self.rbi_batter_id,
                    reason=self.reason or "run",
                )
            ]

        return []


@dataclass(frozen=True)
class RunnerRemovedEvent(GameEvent):
    """
    A runner is removed from the bases (out or scored).
    """

    runner_id: str
    from_base: Optional[int]
    reason: Optional[str] = None

    def apply(self, game):
        game.bases.remove(
            runner_id=self.runner_id,
            from_base=self.from_base,
        )
