# src/game/events/balk.py
from dataclasses import dataclass
from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent


@dataclass(frozen=True)
class BalkEvent(GameEvent):
    def apply(self, game):
        followups = []
        for b in (3, 2, 1):
            runner_id = game.bases.runner_on(b)
            if runner_id:
                followups.append(
                    RunnerAdvancedEvent(
                        runner_id=runner_id,
                        from_base=b,
                        to_base=b + 1,
                        reason="balk",
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"Balk! Runners advance."
