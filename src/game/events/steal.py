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
        # Log or track steal attempts for statistics
        # No state mutation needed here - the outcome events handle that
        # base_names = {1: "second", 2: "third", 3: "home"}
        # game.logger.debug(
        #     f"Steal attempt: {self.runner.name} attempting to steal {base_names.get(self.to_base, str(self.to_base))}"
        # )

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
        # The RunnerAdvancedEvent handles the state mutation
        # This event is for logging/statistics
        # base_names = {1: "first", 2: "second", 3: "third", 4: "home"}
        # game.logger.info(
        #     f"Stolen base! Runner advanced to {base_names.get(self.to_base, str(self.to_base))}"
        # )
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
        # This event is for logging/statistics
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
"""
Example in _resolve_steal_attempt:

    if self.rng.random() < success_prob:
        # Successful steal
        events.append(StealAttemptEvent(runner_id=runner, from_base=from_base, to_base=to_base))
        events.append(StolenBaseEvent(runner_id=runner, from_base=from_base, to_base=to_base))
        events.append(RunnerAdvancedEvent(
            runner_id=runner,
            from_base=from_base,
            to_base=to_base,
            reason="stolen_base",
        ))
        
    else:
        # Caught stealing
        events.append(StealAttemptEvent(runner_id=runner, from_base=from_base, to_base=to_base))
        events.append(CaughtStealingEvent(runner_id=runner, from_base=from_base, to_base=to_base))
        events.append(OutRecordedEvent(reason="caught_stealing"))
        events.append(RunnerRemovedEvent(
            runner_id=runner,
            from_base=from_base,
            reason="caught_stealing",
        ))
"""
