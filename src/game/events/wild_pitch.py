# src/game/events/wild_pitch.py
from dataclasses import dataclass
from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent


@dataclass(frozen=True)
class WildPitchEvent(GameEvent):
    def apply(self, game):
        followups = []
        # TODO Not all runners need to necessarily advance
        # A single runner advancing would be enough
        # For simplicity we now advance them all
        for b in (3, 2, 1):
            runner_id = game.bases.runner_on(b)
            if runner_id:
                followups.append(
                    RunnerAdvancedEvent(
                        runner_id=runner_id,
                        from_base=b,
                        to_base=b + 1,
                        reason="wild_pitch",
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Wild Pitch! Runners advance."
