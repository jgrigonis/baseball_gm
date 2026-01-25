# src/game/events/balk.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class BalkEvent(GameEvent):
    pitcher: PlayerInGame

    def apply(self, game):
        self.pitcher.game_stats.pitching.balk()
        followups = []
        for b in (3, 2, 1):
            runner = game.bases.runner_on(b)
            if runner:
                followups.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=b,
                        to_base=b + 1,
                        reason="balk",
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Balk! Runners advance."
