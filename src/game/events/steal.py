# src/game/events/steal.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


@dataclass
class StealAttemptEvent(GameEvent):
    """Runner attempts to steal a base"""

    runner: PlayerInGame
    from_base: int
    to_base: int

    def apply(self, game):
        """
        Record that a steal attempt occurred.

        This is primarily for statistics/logging.
        The actual outcome (success/caught) is handled by subsequent events.
        """
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        base_names = {1: "second", 2: "third", 3: "home"}
        return f"Steal attempt: {self.runner.name} attempting to steal {base_names.get(self.to_base, str(self.to_base))}"


@dataclass
class StolenBaseEvent(GameEvent):
    """Successful stolen base"""

    runner: PlayerInGame
    from_base: int
    to_base: int

    def apply(self, game):
        """
        Record a successful stolen base.

        Note: The actual runner advancement is handled by
        RunnerAdvancedEvent that follows this event.
        """
        self.runner.game_stats.batting.steal()

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        base_names = {1: "second", 2: "third", 3: "home"}
        return f"Stolen base! Runner advanced to {base_names.get(self.to_base, str(self.to_base))}"


@dataclass
class CaughtStealingEvent(GameEvent):
    """Runner caught stealing"""

    runner: PlayerInGame
    from_base: int
    to_base: int

    def apply(self, game):
        """
        Record a caught stealing.

        Note: The actual out recording and runner removal are handled by
        OutRecordedEvent and RunnerRemovedEvent that follow this event.
        """
        # The OutRecordedEvent and RunnerRemovedEvent handle the state mutation
        self.runner.game_stats.batting.caught_stealing()

    def describe(self, game) -> str:
        base_names = {1: "first", 2: "second", 3: "third", 4: "home"}
        return f"Caught stealing! Runner thrown out attempting to steal {base_names.get(self.to_base, str(self.to_base))}"


@dataclass
class DoubleStealtAttemptEvent(GameEvent):
    """Multiple runners attempting to steal simultaneously"""

    bases: list[int]

    def apply(self, game):
        """
        Record that a double steal was attempted.

        This is primarily for statistics/logging.
        """
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        # Log the double steal attempt
        return f"Double steal attempt on bases: {self.bases}"


"""
DOUBLE STEAL SEQUENCE:
1. DoubleStealtAttemptEvent  - Log double steal attempt
2. StealAttemptEvent (runner 1)
3. StealAttemptEvent (runner 2)
4. Outcome events for each runner (stolen base or caught stealing)

The pattern is:
- "Attempt" event = logging only
- "Outcome" event (Success/Failed/Error/StolenBase/CaughtStealing) = logging only
- State mutation events (OutRecordedEvent, RunnerAdvancedEvent, RunnerRemovedEvent) = actual state changes

This separation allows for:
1. Clean statistics tracking
2. Detailed play-by-play logging
3. Replay/animation systems
4. Separation of concerns (logging vs state mutation)
"""
