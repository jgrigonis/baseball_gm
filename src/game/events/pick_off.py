# src/game/events/pick_off.py
from dataclasses import dataclass

from src.game.event import GameEvent
from src.player.player_in_game import PlayerInGame

# ================================================================
# PICKOFF EVENTS
# ================================================================


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class PickoffErrorEvent(GameEvent):
    """Error on a pickoff - runners advance. `fielder` is charged with it:
    the pitcher for a bad throw, the man at the bag for a drop (the pitcher
    when not given)."""

    base: int
    runner: PlayerInGame
    pitcher: PlayerInGame
    fielder: PlayerInGame | None = None

    def apply(self, game):
        """
        Record a pickoff throwing error.

        Note: The actual runner advancement is handled by
        RunnerAdvancedEvent that follows this event.
        """
        (self.fielder or self.pitcher).game_stats.fielding.error()
        game._inning_had_error = True
        # The RunnerAdvancedEvent handles the state mutation
        # This event is for logging/statistics
        game.logger.info(f"Throwing error on pickoff at base {self.base}")

    def describe(self, game) -> str:
        """Return human-readable description with game context."""
        who = self.fielder or self.pitcher
        if who is self.pitcher:
            return f"{self.pitcher.name} throws the pickoff away!"
        return f"{who.name} drops the pickoff throw!"


@dataclass(frozen=True)
class CatcherPickoffSuccessEvent(GameEvent):
    """The catcher threw behind a runner and got him. The putout, out and
    runner removal follow as their own events."""

    base: int
    runner: PlayerInGame
    catcher: PlayerInGame

    def apply(self, game):
        self.catcher.game_stats.fielding.catcher_pickoff()

    def describe(self, game) -> str:
        return f"{self.catcher.name} picked off {self.runner.name} on {self.base}!"


@dataclass(frozen=True)
class CatcherPickoffErrorEvent(GameEvent):
    """A catcher's pickoff throw went wrong and the runners move up:
    `fielder` is charged, the catcher for a bad throw or the man at the bag
    for a drop."""

    base: int
    runner: PlayerInGame
    catcher: PlayerInGame
    fielder: PlayerInGame

    def apply(self, game):
        self.fielder.game_stats.fielding.error()
        game._inning_had_error = True

    def describe(self, game) -> str:
        if self.fielder is self.catcher:
            return f"{self.catcher.name}'s pickoff throw gets away!"
        return f"{self.fielder.name} drops the catcher's pickoff throw!"


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
