# src/game/game.py
"""
Game orchestration and event processing.

Game owns:
- Game state (inning, count, bases, score)
- Event queue and processing
- Main game loop

Game does NOT:
- Decide outcomes (that's Resolver)
- Enforce baseball rules (that's events + Resolver)
- Manage player stats (that's PlayerInGame)
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from collections import deque
from dataclasses import dataclass
import logging
import random


from src.game.inning import Inning
from src.game.count import Count
from src.game.bases import Bases
from src.game.event import GameEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.intent import GameIntent
from src.game.intent_generator import IntentGenerator
from src.game.intents.pick_off import PickOffIntent
from src.game.intents.pitch import PrePitchSituation
from src.game.resolver import EnhancedResolver
from src.game.score import Score
from src.game.strategy import GameStrategy
from src.player.fatigue import FatigueLevel
from src.player.player_formatters import PlayerTableFormatter
from src.util.logger import setup_logger


if TYPE_CHECKING:
    from src.team.team_in_game import TeamInGame
    from src.player.player_in_game import PlayerInGame


class GameStateError(Exception):
    """Invalid game state detected."""

    pass


@dataclass(frozen=True)
class GameResult:
    """Final game result."""

    home_team: str
    away_team: str
    home_score: int
    away_score: int
    innings_played: int
    winner: str
    winning_margin: int

    def __str__(self) -> str:
        return (
            f"{self.away_team} {self.away_score} @ "
            f"{self.home_team} {self.home_score} "
            f"({'F' if self.innings_played == 9 else f'F/{self.innings_played}'}) "
            f"- {self.winner} wins by {self.winning_margin}"
        )


@dataclass(frozen=True)
class GameContext:
    """Immutable snapshot of current game context."""

    inning_number: int
    inning_top: bool
    balls: int
    strikes: int
    outs: int
    bases_occupied: dict[int, str]
    home_score: int
    away_score: int
    current_batter: str
    current_pitcher: str

    def __str__(self) -> str:
        half = "Top" if self.inning_top else "Bot"
        return (
            f"{half} {self.inning_number} | "
            f"{self.away_score}-{self.home_score} | "
            f"{self.outs} out | "
            f"{self.balls}-{self.strikes} count"
        )


class Game:
    """
    Orchestrates game flow and event processing.

    The game loop processes events one at a time. Events can generate
    follow-up events that are processed immediately (prepended to queue).
    """

    def __init__(
        self,
        home_team: TeamInGame,
        away_team: TeamInGame,
        *,
        rng: random.Random | None = None,
        log_level: int | None = None,
        intent_generator: IntentGenerator | None = None,
        resolver: EnhancedResolver | None = None,
        pauses: bool = False,
    ) -> None:
        """
        Initialize a new game.

        Args:
            home_team: Home team
            away_team: Away team
            rng: Random number generator (default: new Random())
            log_level: Logging level (default: INFO)
            intent_generator: Intent generator (default: new IntentGenerator)
            resolver: Event resolver (default: new Resolver)

        Raises:
            ValueError: If teams are invalid/missing
        """
        # Validate teams
        if home_team is None or away_team is None:
            raise ValueError("Both home and away teams are required")
        if home_team.record.id == away_team.record.id:
            self.logger.debug("Home and away teams are the same")

        # Teams
        self.home = home_team
        self.away = away_team
        self.bat_team = self.away  # Away bats first
        self.pitch_team = self.home

        # setup a name shortcut
        self.home.name = self.home.record.mascot
        self.away.name = self.away.record.mascot

        # Core game state
        self.inning = Inning()
        self.count = Count()
        self.bases = Bases()
        self.score = Score()

        # Event pipeline
        self._queue: deque[GameEvent] = deque()

        # Random number generation
        self.rng = rng or random.Random()

        # Engine components
        self.intent_generator = intent_generator or IntentGenerator(self.rng)
        self.resolver = resolver or EnhancedResolver(self.rng)
        self.situation = PrePitchSituation

        # Current player cursors
        self.current_batter: PlayerInGame | None = None
        self.current_pitcher: PlayerInGame | None = None

        # Plate appearance tracking
        self._plate_appearance_complete = False
        self._pa_end_reason: str | None = None

        # Logging
        self.log_level = log_level or logging.INFO
        self.logger = setup_logger(
            name="game", level=self.log_level, console_level=self.log_level
        )
        self.pauses = pauses

        # Initialize player game stats
        self._init_game_stats()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play(self) -> GameResult:
        """
        Run the game until completion.

        Returns:
            GameResult with final score and winner

        Raises:
            RuntimeError: If lineups are not set
        """
        if not self.home.has_lineup or not self.away.has_lineup:
            raise RuntimeError("Both teams must have lineups before play()")

        self._sync_players()
        self.logger.info("⚾ Play Ball!")
        self.logger.info(
            f"{self.away.record.city} {self.away.record.mascot} @ {self.home.record.city} {self.home.record.mascot}"
        )

        while not self.is_over():
            if self.pauses:
                inpt = input("Press Enter to continue... ")
                self.handle_input(inpt)
            self.step()

        result = self.get_result()
        self.logger.info(
            f"🏆 Game Over - {result.winner} wins {result.home_score}-{result.away_score}"
        )
        self.logger.info(f"\n🏆 Final: {result}")
        if self.log_level in (logging.DEBUG, logging.TRACE):
            self.validate_stats()
        return result

    def step(self) -> None:
        """
        Process one event from the queue, or generate a new intent.

        Flow:
        1. If events queued → process one event
        2. Event may produce follow-up events (prepended to queue)
        3. Follow-ups are processed before pre-existing events
        4. If no events → check for pickoff attempt → generate pitch intent → resolve → enqueue

        Invariants:
        - Exactly one event applied per step
        - Follow-ups execute before queued events (LIFO for follow-ups)
        - PlateAppearanceEndEvent must not have follow-ups
        """
        # Process one queued event
        if self._queue:
            event = self._dequeue()
            self.logger.trace(f"[STEP] Applying → {event}")

            # apply the event and possibly return a list of followups
            followups = event.apply(self) or []

            if event.should_log(self):
                # set level to the specific level for this event
                level = event.log_level()
                if level:
                    self.logger.log(level, event.describe(self))
                else:
                    self.logger.info(event.describe(self))
            else:
                # We still log it in trace level if it doesn't log.
                self.logger.trace(event.describe(self))

            if followups:
                self.logger.trace(
                    f"[STEP] Follow-ups → {[e.label() for e in followups]}"
                )
                self._enqueue_left(followups)

            # Post-event housekeeping
            self._post_event()
            return

        # No queued events → check for pre-pitch plays, then generate pitch intent
        self.situation = GameStrategy.plan_pre_pitch(self, self.rng)

        steal_on = GameStrategy.set_steal(self.situation)

        # Check if pitcher should attempt pickoff (pre-pitch play)
        if self.situation.pickoff_attempt:
            pickoff_intent = PickOffIntent(
                pitcher=self.current_pitcher,
                target_base=self.situation.pickoff_attempt,
                steal_on=steal_on,
            )
            self.logger.trace(f"[STEP] Pre-pitch Intent → {pickoff_intent}")
            events = self._resolve_intent(pickoff_intent)
            self._enqueue(events)
            return

        self.logger.trace(self.situation)
        # Generate pitch intent
        intent = self._next_intent()
        self.logger.trace(f"[STEP] Intent → {intent}")

        events = self._resolve_intent(intent)
        self._enqueue(events)

    def is_over(self) -> bool:
        """
        Check if the game is complete.

        Game ends when:
        - After top of 9th with 3 outs, home team already leading (no need for bottom)
        - In the bottom of 9th or later, home team leading
        - After bottom of 9 or extra inning(s) with 3 outs, away team leading

        Returns:
            True if game is over
        """
        # # Clear the whole queue before ending
        if self._queue:
            return False
        # Must play at least through top of 9th
        if self.inning.number < 9:
            return False

        # Check if a half-inning just completed (3 outs)
        half_inning_complete = self.inning.outs >= 3

        # Top of 9th complete, home leading - no need for bottom 9th
        if (
            self.inning.number == 9
            and self.inning.top
            and half_inning_complete
            and self.score.home > self.score.away
        ):
            return True

        # Bottom of 9th or later, home leading - game over
        if (
            self.inning.number >= 9
            and self.inning.bottom
            and self.score.home > self.score.away
        ):
            return True

        # Bottom half complete, away leading
        if (
            self.inning.number >= 9
            and self.inning.bottom
            and half_inning_complete
            and self.score.away > self.score.home
        ):
            return True

        return False

    def get_result(self) -> GameResult:
        """
        Get final game result.

        Returns:
            GameResult with scores and winner

        Raises:
            RuntimeError: If game is not over
        """
        if not self.is_over():
            raise RuntimeError("Cannot get result - game not over")

        winner = (
            self.home.record.mascot
            if self.score.home > self.score.away
            else self.away.record.mascot
        )
        margin = abs(self.score.home - self.score.away)

        return GameResult(
            home_team=self.home.record.mascot,
            away_team=self.away.record.mascot,
            home_score=self.score.home,
            away_score=self.score.away,
            innings_played=self.inning.number,
            winner=winner,
            winning_margin=margin,
        )

    def get_context(self) -> GameContext:
        """
        Get immutable snapshot of current game state.

        Returns:
            GameContext with current game situation
        """
        return GameContext(
            inning_number=self.inning.number,
            inning_top=self.inning.top,
            balls=self.count.balls,
            strikes=self.count.strikes,
            outs=self.inning.outs,
            bases_occupied=self.bases.occupied_map(),
            home_score=self.score.home,
            away_score=self.score.away,
            current_batter=(
                self.current_batter.player.name if self.current_batter else "None"
            ),
            current_pitcher=(
                self.current_pitcher.name if self.current_pitcher else "None"
            ),
        )

    def get_player(self, player_id: str) -> PlayerInGame:
        """
        Get a player by ID from either team.

        Args:
            player_id: Player's unique ID

        Returns:
            PlayerInGame object

        Raises:
            ValueError: If player not found on either team
        """
        # Check home team
        for player in self.home.players:
            if player.id == player_id:
                return player

        # Check away team
        for player in self.away.players:
            if player.id == player_id:
                return player

        raise ValueError(f"Player {player_id} not found on either team")

    # ------------------------------------------------------------------
    # Pause/Resume Controls
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Enable step-by-step mode (pause after each step)."""
        self.pauses = True
        self.logger.info("⏸️  Game paused - press Enter to step")

    def resume(self) -> None:
        """Disable step-by-step mode."""
        self.pauses = False
        self.logger.info("▶️  Game resumed")

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        if self.pauses:
            self.resume()
        else:
            self.pause()

    def handle_input(self, inpt) -> None:
        """
        Handle input.
        """
        if inpt == "p":
            self.toggle_pause()

    # ------------------------------------------------------------------
    # Post-event Housekeeping
    # ------------------------------------------------------------------

    def _post_event(self) -> None:
        """
        Observe game state after each event and advance structure.

        This is called after EVERY event, including follow-ups.
        Handles:
        - Advancing batter after PA complete
        - Ending half-inning when 3 outs

        Raises:
            GameStateError: If PA complete but events still queued
        """
        self.logger.trace("Entering _post_event")

        # Check for pitching change after plate appearance completes
        if self._plate_appearance_complete and self.current_pitcher:
            if GameStrategy.should_consider_pitching_change(self.current_pitcher):
                self.logger.info(
                    f"⚠️ Manager considering pitching change for {self.current_pitcher.name}"
                )
                # TODO: Implement actual pitching change logic

        # If 3 outs reached, clear remaining queue EXCEPT PlateAppearanceEndEvent
        if self._half_inning_over() and self._queue:
            # Keep only PlateAppearanceEndEvent for stat tracking
            self.logger.trace("Keeping PlateAppearanceEndEvents")
            pa_events = [
                e for e in self._queue if isinstance(e, PlateAppearanceEndEvent)
            ]
            cleared_events = [
                e for e in self._queue if not isinstance(e, PlateAppearanceEndEvent)
            ]

            if cleared_events:
                self.logger.debug(
                    f"Inning over - cleared {len(cleared_events)} events: "
                    f"{[e.label() for e in cleared_events]}"
                )

            self.logger.trace("Clearing queue")
            self._queue.clear()
            if pa_events:
                self.logger.debug(
                    f"Inning over - extending {len(pa_events)} events: "
                    f"{[e.label() for e in pa_events]}"
                )
            self._queue.extend(pa_events)

        # Validate invariant: PA complete → queue empty
        if self._plate_appearance_complete and self._queue:
            queue_contents = [e.label() for e in self._queue]
            raise GameStateError(
                f"PlateAppearanceEndEvent fired with {len(self._queue)} pending events. "
                f"Queue: {queue_contents}"
            )

        # Advance batter if PA is complete
        if self._plate_appearance_complete:
            self._advance_batter()
            self.count.reset()

        # End half-inning if 3 outs reached AND queue is empty
        # This ensures all events (including PlateAppearanceEndEvent) are processed
        if self._half_inning_over() and not self._queue:
            self._end_half_inning()

        self.logger.trace("Leaving _post_event")

    # ------------------------------------------------------------------
    # Intent / Resolution
    # ------------------------------------------------------------------

    def _next_intent(self) -> GameIntent:
        """Generate the next game intent."""
        return self.intent_generator.next_intent(self)

    def _resolve_intent(self, intent: GameIntent) -> list[GameEvent]:
        """
        Resolve intent into events.

        Args:
            intent: Game intent to resolve

        Returns:
            List of events (always non-empty)

        Raises:
            RuntimeError: If resolver returns no events
        """
        events = self.resolver.resolve(intent, self)
        if not events:
            raise RuntimeError("Resolver returned no events")
        return events

    # ------------------------------------------------------------------
    # Event Queue Management
    # ------------------------------------------------------------------

    def _enqueue(self, events: list[GameEvent]) -> None:
        """
        Enqueue events to the back of the queue (FIFO).

        Args:
            events: Events to enqueue

        Raises:
            RuntimeError: If events list is empty
        """
        if not events:
            raise RuntimeError("Cannot enqueue empty event list")

        self._queue.extend(events)
        self.logger.trace(f"[QUEUE] Added {len(events)} events to back")

    def _dequeue(self) -> GameEvent:
        """
        Dequeue one event from the front (FIFO).

        Returns:
            Next event to process
        """
        return self._queue.popleft()

    def _enqueue_left(self, events: list[GameEvent] | GameEvent) -> None:
        """
        Enqueue events to the front of the queue (LIFO for follow-ups).

        Follow-up events are processed before pre-existing events.
        Events are added in reverse order to preserve execution order.

        Args:
            events: Single event or list of events
        """
        if not events:
            return

        if isinstance(events, list):
            # Add in reverse to preserve order
            for event in reversed(events):
                self._queue.appendleft(event)
            self.logger.trace(f"[QUEUE] Prepended {len(events)} follow-ups")
        else:
            self._queue.appendleft(events)
            self.logger.trace("[QUEUE] Prepended 1 follow-up")

    # ------------------------------------------------------------------
    # Game State Queries
    # ------------------------------------------------------------------

    def _half_inning_over(self) -> bool:
        """
        Check if current half-inning should end.

        Returns:
            True if 3 outs recorded
        """
        return self.inning.outs >= 3

    def _is_extra_innings_complete(self) -> bool:
        """
        Check if extra innings are complete.

        Extra innings end after a full inning (top half) with score not tied.

        Returns:
            True if extra innings complete
        """
        if self.inning.number <= 9:
            return False
        if self.inning.bottom:
            return False  # Still in same inning
        if self.score.is_tied:
            return False  # Continue if tied

        return True

    # ------------------------------------------------------------------
    # Game Flow Helpers
    # ------------------------------------------------------------------

    def _advance_batter(self) -> None:
        """Advance to the next batter and reset PA state."""
        self.logger.trace("Advancing to next batter")
        self.logger.trace(
            f"Previous batter: {self.current_batter.player.name if self.current_batter else 'None'}"
        )

        self.current_batter = self._next_batter()
        if self.inning.outs < 3:
            self.logger.info(f"🏏 Batting: {self.current_batter.player.name}")
        self._plate_appearance_complete = False
        self._pa_end_reason = None

        self.logger.trace(f"Next batter: {self.current_batter.player.name}")

    def _end_half_inning(self) -> None:
        """End the current half-inning and transition to next."""

        self.logger.info(f"📊 End of {self.inning}")
        self.logger.info(
            f"Score: {self.away.record.mascot} {self.score.away} - {self.home.record.mascot} {self.score.home}"
        )
        # Check if game is over BEFORE incrementing
        if self.is_over():
            return
        # Advance inning
        self.inning.increment()

        # Reset state
        self.bases.clear()
        self.count.reset()
        # self._queue.clear()

        # Swap teams
        self._swap_teams()
        self._sync_players()

        self.logger.info(f"⚾ {self.inning}")

    def _swap_teams(self) -> None:
        """Swap batting and pitching teams."""
        self.bat_team, self.pitch_team = self.pitch_team, self.bat_team
        self.logger.debug(f"Teams swapped - now batting: {self.bat_team.record.mascot}")

    def _next_batter(self) -> PlayerInGame:
        """
        Get the next batter from the lineup.

        Returns:
            Next PlayerInGame to bat
        """
        return self.bat_team.next_batter()

    def _mark_plate_appearance_complete(self, reason: str) -> None:
        """
        Mark the current plate appearance as complete.

        Args:
            reason: Why the PA ended (e.g., "strikeout", "walk", "hit")
        """
        self._plate_appearance_complete = True
        self._pa_end_reason = reason
        self.logger.trace(f"PA complete: {reason}")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_game_stats(self) -> None:
        """Initialize game stats for all players on both teams."""
        for player in self.away.players + self.home.players:
            player.init_game_stats()
        self.logger.debug("Game stats initialized for all players")

    def _sync_players(self) -> None:
        """Sync current batter and pitcher from lineups."""
        self.current_batter = self.bat_team.current_batter
        self.current_pitcher = self.pitch_team.current_pitcher

        self.logger.info(f"🏏 Batting: {self.current_batter.player.name}")
        self.logger.info(f"⚾ Pitching: {self.current_pitcher.name}")
        # Fatigue info
        if self.current_pitcher.pitcher_fatigue:
            fatigue = self.current_pitcher.pitcher_fatigue
            self.logger.info(
                f"⚾ Pitching: {self.current_pitcher.name} "
                f"({fatigue.pitches_thrown}P, {fatigue.get_level().value})"
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def batting_team_name(self) -> str:
        """Name of team currently batting."""
        return self.bat_team.record.city + " " + self.bat_team.record.mascot

    @property
    def pitching_team_name(self) -> str:
        """Name of team currently pitching."""
        return self.pitch_team.record.city + " " + self.pitch_team.record.mascot

    @property
    def inning_state(self) -> str:
        """Formatted inning state (e.g., 'Top 3rd')."""
        return str(self.inning)

    @property
    def game_state_summary(self) -> str:
        """One-line game state summary."""
        return (
            f"{self.inning} | "
            f"{self.away.name} {self.score.away} @ {self.home.name} {self.score.home} | "
            f"{self.bases} | "
            f"{self.inning.outs} out | "
            f"Count: {self.count}"
        )

    # ------------------------------------------------------------------
    # Debug Helpers
    # ------------------------------------------------------------------

    def _debug_queue(self, prefix: str = "") -> None:
        """
        Log current queue contents.

        Args:
            prefix: Prefix for log message
        """
        if not self.logger.isEnabledFor(logging.DEBUG):
            return

        contents = [e.label() for e in self._queue]
        self.logger.debug(f"{prefix}QUEUE = {contents}")

    def print_state(self) -> None:
        """Print current game state (for debugging)."""
        print("\n" + "=" * 60)
        print(f"Game State: {self.game_state_summary}")
        print(f"Context: {self.get_context()}")
        print("=" * 60 + "\n")

    def validate_stats(self):
        """Validate stats."""
        for player in self.home.players + self.away.players:
            if (
                player.game_stats.batting.at_bats
                + player.game_stats.batting.walks
                + player.game_stats.batting.hbp
                + player.game_stats.batting.sac_bunts
                + player.game_stats.batting.sac_flys
                + player.game_stats.batting.catcher_interferences
                != player.game_stats.batting.plate_appearances
            ):
                print(PlayerTableFormatter.horizontal_stat_header())
                print(PlayerTableFormatter.horizontal_stats(player))
                raise GameStateError(
                    f"Plate appearances don't add up for {player.name}"
                )

    def check_pitcher_fatigue(self) -> FatigueLevel:
        """Check current pitcher's fatigue level."""
        if self.current_pitcher and self.current_pitcher.pitcher_fatigue:
            return self.current_pitcher.pitcher_fatigue.get_level()
        return FatigueLevel.FRESH
