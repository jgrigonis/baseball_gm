# src/game/events/pick_off.py
from dataclasses import dataclass
from src.game.event import GameEvent


# ================================================================
# PICKOFF EVENTS
# ================================================================


@dataclass
class PickoffAttemptEvent(GameEvent):
    """Pitcher attempts to pick off a runner"""

    base: int
    runner_id: str

    def apply(self, game):
        """
        Record that a pickoff attempt occurred.

        This is primarily for statistics/logging.
        The actual outcome (success/failure/error) is handled by subsequent events.
        """
        # Log or track pickoff attempts for statistics
        # No state mutation needed here - the outcome events handle that
        pass

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return (
            f"{game.current_pitcher.name} tried to pick off the runner on {self.base}."
        )


@dataclass
class PickoffSuccessEvent(GameEvent):
    """Successful pickoff - runner out"""

    base: int
    runner_id: str

    def apply(self, game):
        """
        Record a successful pickoff.

        Note: The actual out recording and runner removal are handled by
        OutRecordedEvent and RunnerRemovedEvent that follow this event.
        """
        # The OutRecordedEvent and RunnerRemovedEvent handle the state mutation
        # This event is for logging/statistics
        game.logger.info(f"Runner picked off at base {self.base}")

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{game.current_pitcher.name} picked off the runner on {self.base}."


@dataclass
class PickoffFailedEvent(GameEvent):
    """Failed pickoff attempt - runner safe"""

    base: int
    runner_id: str

    def apply(self, game):
        """
        Record a failed pickoff attempt.

        Runner remains safe on the base.
        """
        # No state change - runner stays where they are
        game.logger.debug(f"Pickoff attempt failed at base {self.base}")

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "Pickoff failed."


@dataclass
class PickoffErrorEvent(GameEvent):
    """Throwing error on pickoff - runner advances"""

    base: int
    runner_id: str

    def apply(self, game):
        """
        Record a pickoff throwing error.

        Note: The actual runner advancement is handled by
        RunnerAdvancedEvent that follows this event.
        """
        # The RunnerAdvancedEvent handles the state mutation
        # This event is for logging/statistics
        game.logger.info(f"Throwing error on pickoff at base {self.base}")

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return "An error on the pickoff!"


"""
Event Ordering Pattern:

PICKOFF SEQUENCE:
1. PickoffAttemptEvent       - Log that attempt happened
2a. PickoffSuccessEvent      - Log success
    OutRecordedEvent         - Increment outs
    RunnerRemovedEvent       - Remove runner from base
OR
2b. PickoffFailedEvent       - Log failure (no state change)
OR
2c. PickoffErrorEvent        - Log error
    RunnerAdvancedEvent      - Move runner forward

STEAL SEQUENCE:
1. StealAttemptEvent         - Log that attempt happened
2a. StolenBaseEvent          - Log success
    RunnerAdvancedEvent      - Move runner to new base
OR
2b. CaughtStealingEvent      - Log caught stealing
    OutRecordedEvent         - Increment outs
    RunnerRemovedEvent       - Remove runner from base

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
Example in _resolve_pickoff_attempt:

    if r < self.PICKOFF_SUCCESS_PROB:
        # Successful pickoff - runner out
        events.append(PickoffAttemptEvent(base=base, runner_id=runner))
        events.append(PickoffSuccessEvent(base=base, runner_id=runner))
        events.append(OutRecordedEvent(reason="pickoff"))
        events.append(RunnerRemovedEvent(runner_id=runner, from_base=base, reason="pickoff"))
        
    elif r < self.PICKOFF_SUCCESS_PROB + self.PICKOFF_ERROR_PROB:
        # Throwing error - runner advances
        events.append(PickoffAttemptEvent(base=base, runner_id=runner))
        events.append(PickoffErrorEvent(base=base, runner_id=runner))
        events.append(RunnerAdvancedEvent(
            runner_id=runner,
            from_base=base,
            to_base=min(base + 1, HOME),
            reason="pickoff_error",
        ))
        
    else:
        # Runner safe, no advancement
        events.append(PickoffAttemptEvent(base=base, runner_id=runner))
        events.append(PickoffFailedEvent(base=base, runner_id=runner))

"""
