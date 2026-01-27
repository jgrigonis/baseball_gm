# src/game/events/pick_off.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame


# ================================================================
# PICKOFF EVENTS
# ================================================================


@dataclass
class PickoffAttemptEvent(GameEvent):
    """Pitcher attempts to pick off a runner"""

    base: int
    runner: PlayerInGame
    pitcher: PlayerInGame

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
            f"{self.pitcher.name} tried to pick off {self.runner.name} on {self.base}."
        )


@dataclass
class PickoffSuccessEvent(GameEvent):
    """Successful pickoff - runner out"""

    base: int
    runner: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        """
        Record a successful pickoff.

        Note: The actual out recording and runner removal are handled by
        OutRecordedEvent and RunnerRemovedEvent that follow this event.
        """
        self.pitcher.game_stats.pitching.pickoff()
        # The OutRecordedEvent and RunnerRemovedEvent handle the state mutation
        # This event is for logging/statistics
        game.logger.info(f"Runner picked off at base {self.base}")

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        return f"{self.pitcher.name} picked off {self.runner.name} on {self.base}."


@dataclass
class PickoffFailedEvent(GameEvent):
    """Failed pickoff attempt - runner safe"""

    base: int
    runner: PlayerInGame
    pitcher: PlayerInGame

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
    runner: PlayerInGame
    pitcher: PlayerInGame

    def apply(self, game):
        """
        Record a pickoff throwing error.

        Note: The actual runner advancement is handled by
        RunnerAdvancedEvent that follows this event.
        """
        self.pitcher.game_stats.fielding.error()
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