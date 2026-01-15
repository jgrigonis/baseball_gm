# src/game/events/bases.py
from dataclasses import dataclass
from typing import Optional

from src.game.event import GameEvent


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

    def apply(self, game):
        game.bases.advance(
            runner_id=self.runner_id,
            from_base=self.from_base,
            to_base=self.to_base,
        )


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
