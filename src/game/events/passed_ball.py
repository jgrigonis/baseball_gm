# src/game/events/passed_ball.py
from dataclasses import dataclass

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class PassedBallEvent(GameEvent):
    """
    This tracks the stats for the catcher, but it also
    advances all runners one base.
    """

    catcher: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        self.catcher.game_stats.fielding.passed_ball()
        followups = []
        # TODO Not all runners need to necessarily advance
        # A single runner advancing would be enough
        # For simplicity we now advance them all
        for b in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(b)
            if runner:
                followups.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=b,
                        to_base=b + 1,
                        reason="passed_ball",
                        pitcher=self.pitcher,
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Passed Ball! Runners advance."
