# src/game/events/wild_pitch.py
from dataclasses import dataclass

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.runners import RunnerAdvancedEvent
from src.player.player_in_game import PlayerInGame


@dataclass(frozen=True)
class WildPitchEvent(GameEvent):
    """
    Pitcher throws a wild pitch. This advances all runners.
    TODO is to do selective advancements.
    """

    pitcher: PlayerInGame

    def apply(self, game):
        self.pitcher.game_stats.pitching.wild_pitch()
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
                        reason="wild_pitch",
                        pitcher=self.pitcher,
                    )
                )
        return followups

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Wild Pitch! Runners advance."
