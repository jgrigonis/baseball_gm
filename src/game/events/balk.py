# src/game/events/balk.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class BalkEvent(GameEvent):
    """
    This should only ever occur with runners on base.

    Any balk action with no runners on would be an illegal pitch.
    An illegal pitch results in a ball.

    Every runner on base is awarded one base.
    """

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
                        pitcher=self.pitcher,
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Balk! Runners advance."
