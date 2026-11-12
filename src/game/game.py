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
from datetime import date
import logging
import random

from src.db.repositories.pitcher_state import PitcherState
from src.db.repositories.player_energy import PlayerEnergyState
from src.game import bench
from src.game.inning import Inning
from src.game.count import Count
from src.game.bases import SECOND, Bases
from src.game.event import GameEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.game_event_logger import GameEventLogger
from src.game.game_result_resolver import GameResultResolver, PitchingDecisions
from src.game.intent import GameIntent
from src.game.intent_generator import IntentGenerator
from src.game.intents.pick_off import PickOffIntent
from src.game.intents.pitch import PrePitchSituation
from src.game.pitcher_appearance import PitcherAppearance, LeadChange
from src.game.play_log import PlayLog
from src.game.probabilities import (
    INJURY_BASE_PROB,
    FATIGUE_MULTIPLIER,
    LOW_ENERGY,
    BASE_ENERGY_DEPLETION,
    DURABILITY_MOD,
    FREE_STREAK_DAYS,
    MAX_STREAK_PENALTY,
    ENERGY_PENALTY_PER_STREAK_DAY,
    MINOR_INJURY_PROB,
    MODERATE_INJURY_PROB,
    # PITCHER_INJURY_PROB, # use this soon...
    SEVERE_INJURE_PROB,
    SURGERY_INJURY_PROB,
    INJURY_ACTIVITY_WEIGHT,
    INJURY_POSITION_WEIGHT,
)
from src.game.resolver import Resolver
from src.game.score import Score
from src.game.strategy import GameStrategy
from src.game.win_expectancy import home_win_prob, run_expectancy
from src.team.manager_profile import profile_of
from src.player.fatigue import FatigueLevel
from src.player.injury_types import choose_injury_type, injury_label
from src.player.player_formatters import PlayerTableFormatter
from src.util.weighted_choice import WeightedChoice

if TYPE_CHECKING:
    from src.team.team_in_game import TeamInGame
    from src.player.player_in_game import PlayerInGame


# Regular-season extra innings: from this inning on, each half-inning starts
# with a runner on second.
GHOST_RUNNER_INNING = 10


class GameStateError(Exception):
    """Invalid game state detected."""

    pass


POS_MAP = {
    "ss": lambda g: g.pitch_team.current_shortstop,
    "2b": lambda g: g.pitch_team.current_second_baseman,
    "3b": lambda g: g.pitch_team.current_third_baseman,
    "1b": lambda g: g.pitch_team.current_first_baseman,
    "p": lambda g: g.current_pitcher,
    "c": lambda g: g.pitch_team.current_catcher,
    "lf": lambda g: g.pitch_team.current_left_fielder,
    "cf": lambda g: g.pitch_team.current_center_fielder,
    "rf": lambda g: g.pitch_team.current_right_fielder,
    "dh": lambda g: g.pitch_team.current_dh,
}


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
    # Runs by inning; an inning past the last one either side scored in may
    # be missing (Score only fills innings up to the last run).
    away_innings: tuple[int, ...] = ()
    home_innings: tuple[int, ...] = ()

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
        logger: logging.Logger = logging.getLogger("game"),
        intent_generator: IntentGenerator | None = None,
        resolver: Resolver | None = None,
        pauses: bool = False,
        pitcher_states: dict[str, PitcherState] | None = None,
        game_date: date | None = None,
        player_energy_states: dict[str, PlayerEnergyState] | None = None,
        injured_ids: set[str] | None = None,
        event_logger: GameEventLogger | None = None,
        home_eligible: set[str] | None = None,
        away_eligible: set[str] | None = None,
        injuries_enabled: bool = True,
        max_pitcher_outs: int | None = None,
        ghost_runner: bool = False,
        max_innings: int | None = None,
        injury_mults: dict[str, float] | None = None,
        analytics_levels: dict[str, int] | None = None,
    ) -> None:
        """
        Initialize a new game.

        Args:
            home_team: Home team
            away_team: Away team
            rng: Random number generator (default: new Random())
            logger: The log handler to use
            intent_generator: Intent generator (default: new IntentGenerator)
            resolver: Event resolver (default: new Resolver)
            pauses: Whether or not to pause at every opportunity in CLI version (default: False)
            pitcher_states: A dictionary of PitcherStates (default: None)
            game_date: The in game date of the game (default: None)
            player_energy_states: A dictionary of PlayerEnergyStates (default: None)
            injured_ids: A set of player_ids of injured players (default: None)
            event_logger: The GameEventLogger to write to (default: None)
            home_eligible: A set of player_ids eligible to play on the home team (default: None)
            away_eligible: A set of player_ids eligible to play on the away team (default: None)
            injuries_enabled: Whether players can get hurt in this game (default: True)
            max_pitcher_outs: Every pitcher comes out once he has this many outs,
                if there's anyone left to bring in (default: None, no cap)
            ghost_runner: Use the extra-innings rule: from the 10th on, each
                half-inning starts with a runner on second (default: False)
            max_innings: Stop after this many innings even if it's tied, and
                leave the tie to the caller (the All-Star Game's swing-off)
                (default: None, play until someone wins)
            injury_mults: Each team's injury chance multiplier, by team id,
                from its Facilities department (src/league/budget.py)
                (default: None, 1.0 for both)
            analytics_levels: Each team's Analytics level, by team id, which
                aims its steals and hit and runs (src/league/budget.py)
                (default: None, Standard for both)

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
        self.home_eligible = home_eligible
        self.away_eligible = away_eligible

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
        self.resolver = resolver or Resolver(self.rng)
        self.situation = PrePitchSituation

        # Current player cursors
        self.current_batter: PlayerInGame | None = None
        self.current_pitcher: PlayerInGame | None = None

        # Plate appearance tracking
        self._plate_appearance_complete = False
        self._pa_end_reason: str | None = None
        # The state when the current batter came up, for WPA and RE24
        # (_close_segment): inning, top, outs, bases mask, home minus away,
        # batting team's runs.
        self._seg: tuple | None = None

        # Pitcher appearance and lead change tracking
        self.pitcher_appearances: list[PitcherAppearance] = []
        self._active_pitchers: dict[str, PlayerInGame] = {}  # team_id → current pitcher
        self.lead_changes: list[LeadChange] = []
        self._last_known_leader: str = "tied"  # "home", "away", "tied"
        self.decisions: PitchingDecisions | None = None
        self.pitcher_states = pitcher_states or {}
        self.game_date = game_date
        self.player_energy_states = player_energy_states or {}
        self.batters_this_game: set[str] = set()
        self._inning_had_error = False  # reset each half-inning

        # Injury info
        self.injured_ids = set(injured_ids or {})
        self.injuries_enabled = injuries_enabled
        self.injury_mults = injury_mults or {}
        self.analytics_levels = analytics_levels or {}
        self.max_pitcher_outs = max_pitcher_outs
        self.ghost_runner = ghost_runner
        self.max_innings = max_innings
        # (player_id, severity, activity, injury_type)
        self.new_injuries: list[tuple[str, str, str, str | None]] = []

        # Logging
        self.logger = logger
        self.pauses = pauses
        self.event_logger = event_logger
        # Play-by-play, one entry per plate appearance (src/game/play_log.py)
        self.play_log = PlayLog()

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
        self._open_pitcher_appearance(self.current_pitcher)
        self._log_starting_lineups()
        self.logger.info("⚾ Play Ball!")
        self.logger.info(
            f"{self.away.record.city} {self.away.record.mascot} @ {self.home.record.city} {self.home.record.mascot}"
        )

        while not self.is_over():
            if self.pauses:
                inpt = input("Press Enter to continue... ")
                self.handle_input(inpt)
            self.step()
        if self._seg is not None:
            self._close_segment()
        self.play_log.end_half(self)

        for team_id in set(a.team_id for a in self.pitcher_appearances):
            last = next(
                a for a in reversed(self.pitcher_appearances) if a.team_id == team_id
            )
            last.finished_game = True

        result = self.get_result()
        self.logger.info(
            f"🏆 Game Over - {result.winner} wins {result.home_score}-{result.away_score}"
        )
        self.logger.info(f"\n🏆 Final: {result}")
        if self.logger.isEnabledFor(logging.DEBUG):
            self.validate_stats()

        if self.score.is_tied:
            # Stopped at max_innings: nobody wins, so no W, L, save or holds.
            self._credit_complete_games()
            self.decisions = PitchingDecisions()
            return result

        home_wins = self.score.home > self.score.away
        winning_team_id = self.home.record.id if home_wins else self.away.record.id
        losing_team_id = self.away.record.id if home_wins else self.home.record.id
        winning_score = max(self.score.home, self.score.away)
        losing_score = min(self.score.home, self.score.away)

        decisions = GameResultResolver.resolve(
            pitcher_appearances=self.pitcher_appearances,
            lead_changes=self.lead_changes,
            winning_team_id=winning_team_id,
            losing_team_id=losing_team_id,
            winning_score=winning_score,
            losing_score=losing_score,
        )

        if decisions.win:
            decisions.win.pitcher.game_stats.pitching.win = 1
        if decisions.loss:
            decisions.loss.pitcher.game_stats.pitching.loss = 1
        if decisions.save:
            decisions.save.pitcher.game_stats.pitching.save = 1
        for hold in decisions.holds:
            hold.pitcher.game_stats.pitching.hold = 1

        self._credit_complete_games()
        self.decisions = decisions

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
            self.play_log.see(event, self)

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

        # A new batter (or the same one, to start an inning): his manager may
        # send up a pinch hitter, then note the state for WPA and RE24.
        if self._seg is None:
            self._consider_pinch_hitter()
            self._seg = self._seg_state()

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

        # Tied after the last inning there is: the caller breaks the tie.
        if (
            self.max_innings
            and self.inning.number >= self.max_innings
            and self.inning.bottom
            and half_inning_complete
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

        if self.score.is_tied:
            winner = "Nobody"
        elif self.score.home > self.score.away:
            winner = self.home.record.mascot
        else:
            winner = self.away.record.mascot
        margin = abs(self.score.home - self.score.away)

        return GameResult(
            home_team=self.home.record.mascot,
            away_team=self.away.record.mascot,
            home_score=self.score.home,
            away_score=self.score.away,
            innings_played=self.inning.number,
            winner=winner,
            winning_margin=margin,
            away_innings=tuple(self.score.away_innings),
            home_innings=tuple(self.score.home_innings),
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

        # Credit WPA and RE24 for the plate appearance (or the play that
        # ended the half-inning or the game) before anyone is replaced.
        if self._seg is not None and (
            self._plate_appearance_complete
            or self._half_inning_over()
            or self.is_over()
        ):
            self._close_segment()

        # Check for pitching change after plate appearance completes
        if (
            self._plate_appearance_complete
            and self.current_pitcher
            and not self._half_inning_over()
        ):
            self._consider_pitching_change()

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

    def pos(self, position: str) -> PlayerInGame:
        """Get fielder by position."""
        return POS_MAP[position](self)

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

    def _seg_state(self) -> tuple:
        mask = sum(1 << (b - 1) for b in self.bases.occupied_map())
        bat_runs = self.score.away if self.inning.top else self.score.home
        return (
            self.inning.number,
            self.inning.top,
            self.inning.outs,
            mask,
            self.score.home - self.score.away,
            bat_runs,
        )

    def _close_segment(self) -> None:
        """Credit the batter and pitcher with how much the plate appearance
        (steals and wild pitches during it included) moved the batting
        team's chance of winning (WPA) and its expected runs (RE24). The
        pitcher gets the opposite: what he saved."""
        inning, top, outs0, bases0, diff0, runs0 = self._seg
        _, _, outs1, bases1, diff1, runs1 = self._seg_state()
        self._seg = None
        slot, pitcher = self.current_batter, self.current_pitcher
        if slot is None or pitcher is None:
            return
        batter = slot.player
        ghost = bool(self.ghost_runner)
        home0 = home_win_prob(inning, top, outs0, bases0, diff0, ghost)
        if self.is_over():
            home1 = 1.0 if diff1 > 0 else 0.0 if diff1 < 0 else 0.5
        else:
            home1 = home_win_prob(inning, top, min(outs1, 3), bases1, diff1, ghost)
        wpa = (home0 - home1) if top else (home1 - home0)
        re24 = (
            run_expectancy(bases1, outs1)
            - run_expectancy(bases0, outs0)
            + (runs1 - runs0)
        )
        batter.game_stats.batting.wpa += wpa
        batter.game_stats.batting.re24 += re24
        pitcher.game_stats.pitching.wpa -= wpa
        pitcher.game_stats.pitching.re24 -= re24

    def _end_half_inning(self) -> None:
        """End the current half-inning and transition to next."""

        self.logger.info(f"📊 End of {self.inning}")
        self.logger.info(
            f"Score: {self.away.record.mascot} {self.score.away} - {self.home.record.mascot} {self.score.home}"
        )
        # Check if game is over BEFORE incrementing
        if self.is_over():
            return
        self.play_log.end_half(self)
        # Advance inning
        self.inning.increment()
        if self.event_logger:
            self.event_logger.set_context(
                self.inning.number,
                "top" if self.inning.top else "bottom",
            )

        # Reset state
        self.bases.clear()
        self.count.reset()
        self._inning_had_error = False  # reset each half-inning

        # Swap teams
        self._swap_teams()
        self._sync_players()
        self._open_pitcher_appearance(self.current_pitcher)
        # manager can change before inning starts
        self._consider_pitching_change(inning_start=True)

        self.logger.info(f"⚾ {self.inning}")
        if self.ghost_runner and self.inning.number >= GHOST_RUNNER_INNING:
            self._place_ghost_runner()

    def _place_ghost_runner(self) -> None:
        """Extra-innings rule: put a runner on second to start the half-inning.

        He's the batter in the lineup spot just before this inning's leadoff
        hitter (usually the one who made the last out). His run is charged
        to the pitcher on the mound now, but it's unearned.
        """
        lineup = self.bat_team.lineup
        slot = lineup[(self.bat_team.batter_index - 1) % len(lineup)]
        runner = slot.player
        runner.responsible_pitcher = self.current_pitcher
        runner.ghost_runner = True
        self.bases.advance(runner=runner, from_base=None, to_base=SECOND)
        self.logger.info(f"👻 {runner.name} starts the inning on second")

    def _live_energy(self, player) -> float | None:
        """Position player's in-game energy, or None for pitchers."""
        if not player.player_energy:
            return None
        state = self.player_energy_states.get(player.id)
        return state.current_energy if state else player.player_energy.energy

    def _injury_probability(self, player, activity: str) -> float:
        """Chance this player gets hurt on this play doing `activity`."""
        # Compute probability with activity and position weights
        activity_mult = INJURY_ACTIVITY_WEIGHT.get(activity, 1.0)
        if activity == "fielding":
            pos = getattr(player, "current_position", None) or ""
            pos_mult = INJURY_POSITION_WEIGHT.get(pos, 1.0)
            activity_mult *= pos_mult

        # Durable players (pitchers too, when pitching) get hurt less often.
        durability = (
            player.skills.get("durability", 50) if hasattr(player, "skills") else 50
        )
        activity_mult *= 1.0 - ((durability - 50) / 50) * DURABILITY_MOD

        # Tired position players get hurt more often. Pitchers have no
        # player_energy (their fatigue is handled separately), so this
        # never applies to them, even when they bat or run.
        energy = self._live_energy(player)
        if energy is not None:
            activity_mult *= player.player_energy.get_injury_risk_multiplier(energy)

        # A tired pitcher is a little more likely to get hurt pitching.
        fatigue = getattr(player, "pitcher_fatigue", None)
        if activity == "pitching" and fatigue is not None:
            activity_mult *= fatigue.get_injury_risk_multiplier()

        return INJURY_BASE_PROB * activity_mult

    def _check_injuries(self, reason: str = None) -> None:
        """Random injury check for active position players."""
        if not self.injuries_enabled:
            return
        self.logger.debug(f"Checking injuries. reason: {reason}")

        # Build candidates as (player, activity) tuples
        candidates: list[tuple] = []

        # Each candidate carries his team, for its Facilities multiplier.
        bat_id = self.bat_team.record.id
        pitch_id = self.pitch_team.record.id
        if self.current_batter:
            candidates.append((self.current_batter.player, "batting", bat_id))

        for runner in self.bases.runners():
            candidates.append((runner, "running", bat_id))

        if self.current_pitcher:
            candidates.append((self.current_pitcher, "pitching", pitch_id))

        for slot in self.pitch_team.lineup:
            if slot.position == "dh":
                continue
            player = slot.player
            if any(player.id == c[0].id for c in candidates):
                continue
            candidates.append((player, "fielding", pitch_id))

        for player, activity, team_id in candidates:
            if getattr(player, "is_injured", False):
                continue

            prob = self._injury_probability(player, activity)
            prob *= self.injury_mults.get(team_id, 1.0)
            if prob <= 0:
                continue

            if self.rng.random() < prob:
                player.is_injured = True
                severity_roll = WeightedChoice(rng=self.rng)
                severity_roll.set_weights(
                    {
                        "minor": MINOR_INJURY_PROB,
                        "moderate": MODERATE_INJURY_PROB,
                        "severe": SEVERE_INJURE_PROB,
                        "surgery": SURGERY_INJURY_PROB,
                    }
                )
                energy = self._live_energy(player)
                if energy is not None and energy < LOW_ENERGY:
                    severity_roll.multiply("moderate", FATIGUE_MULTIPLIER)
                    severity_roll.multiply("severe", FATIGUE_MULTIPLIER)
                    severity_roll.multiply("surgery", FATIGUE_MULTIPLIER)

                severity = severity_roll.choose()
                kind = choose_injury_type(
                    severity,
                    activity,
                    getattr(player, "current_position", None),
                    rng=self.rng,
                )
                injury_type = kind.key if kind else None
                self.new_injuries.append((player.id, severity, activity, injury_type))
                if self.event_logger:
                    team_id = (
                        self.bat_team.record.id
                        if activity == "batting"
                        else (
                            self.pitch_team.record.id
                            if activity == "pitching"
                            else next(
                                (
                                    t.record.id
                                    for t in [self.bat_team, self.pitch_team]
                                    if any(s.player.id == player.id for s in t.lineup)
                                ),
                                self.pitch_team.record.id,
                            )
                        )
                    )
                    self.event_logger.injury(
                        team_id=team_id,
                        player_id=player.id,
                        name=player.name,
                        severity=severity,
                        activity=activity,
                        injury_type=injury_type,
                    )

                state = self.player_energy_states.get(player.id)
                if state:
                    # injured player energy will drop to 0.75
                    state.current_energy = min(0.75, state.current_energy)

                self.logger.info(
                    f"🚑 {player.name} injured ({activity}): "
                    f"{injury_label(injury_type, severity)}. Severity: {severity}"
                )

                if player.pitcher_fatigue:
                    self._consider_pitching_change(force=True)
                else:
                    for team in [self.bat_team, self.pitch_team]:
                        slot = next(
                            (s for s in team.lineup if s.player.id == player.id), None
                        )
                        if slot:
                            sub = team.get_bench_player(player)
                            if sub:
                                self.logger.info(
                                    f"↔️ {sub.name} enters for {player.name}"
                                )
                                self.logger.info(
                                    f"↔️ {sub.name} enters for {player.name}"
                                )
                                if self.event_logger:
                                    self.event_logger.substitution(
                                        team_id=team.record.id,
                                        incoming_id=sub.id,
                                        incoming_name=sub.name,
                                        outgoing_id=player.id,
                                        outgoing_name=player.name,
                                        position=player.current_position or "?",
                                    )
                                team.substitute(player, sub)
                            break

    def _consider_pinch_hitter(self) -> None:
        """Before a plate appearance: send up a bench bat for the man due up
        if the spot calls for it (src/game/bench.py). He takes the batting
        slot and the position for the rest of the game."""
        slot = self.current_batter
        if slot is None:
            return
        sub = bench.pinch_hitter(self)
        if sub is None:
            return
        batter = slot.player
        position = batter.current_position or slot.position
        self.logger.info(f"🔁 Pinch hitter {sub.name} bats for {batter.name}")
        if self.event_logger:
            self.event_logger.substitution(
                team_id=self.bat_team.record.id,
                incoming_id=sub.id,
                incoming_name=sub.name,
                outgoing_id=batter.id,
                outgoing_name=batter.name,
                position=position or "?",
                kind="ph",
            )
        self.bat_team.substitute(batter, sub)

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
        self._deplete_batter_energy()
        self._check_injuries(reason)

    def _deplete_batter_energy(self) -> None:
        if not self.current_batter:
            return
        player_id = self.current_batter.player.id
        state = self.player_energy_states.get(player_id)
        if not state:
            return
        # No penalty for first few consecutive days, then ramps up
        streak_days = max(0, state.consecutive_days - FREE_STREAK_DAYS)
        streak_penalty = min(
            ENERGY_PENALTY_PER_STREAK_DAY * streak_days, MAX_STREAK_PENALTY
        )
        state.current_energy = max(
            0.0, state.current_energy - BASE_ENERGY_DEPLETION - streak_penalty
        )
        self.batters_this_game.add(player_id)

    def _record_lead_change_if_needed(self, responsible_pitcher) -> None:
        scoring_team = "away" if self.inning.top else "home"
        leader = self.score.leader  # already updated by score_run

        if leader == scoring_team and self._last_known_leader != scoring_team:
            self.lead_changes.append(
                LeadChange(
                    inning=self.inning.number,
                    half="top" if self.inning.top else "bottom",
                    new_leader=scoring_team,
                    responsible_pitcher=responsible_pitcher,
                )
            )

        self._last_known_leader = leader

    def _credit_complete_games(self) -> None:
        """A starter who was his team's only pitcher threw a complete game.
        Allowing no runs makes it a shutout, and no hits over at least nine
        innings a no-hitter."""
        for team_id in {a.team_id for a in self.pitcher_appearances}:
            pitchers = {
                a.pitcher for a in self.pitcher_appearances if a.team_id == team_id
            }
            if len(pitchers) != 1:
                continue
            p = next(iter(pitchers)).game_stats.pitching
            if not p.game_started:
                continue
            p.complete_game = 1
            if p.runs == 0:
                p.shut_out = 1
            if p.hits == 0 and p.outs >= 27:
                p.no_hitter = 1

    def _open_pitcher_appearance(self, pitcher) -> None:
        already_appearing = any(
            a.pitcher == pitcher and not a.finished_game
            for a in self.pitcher_appearances
        )
        if already_appearing:
            return
        self.pitcher_appearances.append(
            PitcherAppearance(
                pitcher=pitcher,
                team_id=self.pitch_team.record.id,
                entered_inning=self.inning.number,
                lead_at_entry=self.score_differential,
                runners_at_entry=self.bases.number_of_baserunners,
            )
        )

    def _note_run_against_pitcher(self) -> None:
        """After a run scores: if it tied the game or put the pitching team
        behind, the pitcher on the mound gave up the lead (whoever put the
        runner on). That costs him a hold or a save."""
        if self.score_differential > 0:
            return
        team_id = self.pitch_team.record.id
        current = next(
            (a for a in reversed(self.pitcher_appearances) if a.team_id == team_id),
            None,
        )
        if current is not None:
            current.lead_lost = True

    def _close_pitcher_appearance(self) -> None:
        """End a pitching appearance, set the most recent pitcher's finished_game to False."""
        if self.pitcher_appearances:
            self.pitcher_appearances[-1].finished_game = False

    def _consider_pitching_change(
        self, force: bool = False, inning_start: bool = False
    ) -> None:
        """Evaluate and possibly make a pitching change. Called mid-inning and between innings.
        If force=True (e.g. pitcher just got injured), skip the probability roll and change immediately.
        """
        if not self.current_pitcher:
            return
        if (
            self.max_pitcher_outs
            and self.current_pitcher.game_stats.pitching.outs >= self.max_pitcher_outs
        ):
            force = True

        # ── Closer situation: override fatigue logic entirely ──────────────
        # find_closer uses the same player pool for both the availability check
        # and the selection, so we can never confirm a closer exists then fail
        # to bring them in (which would cause repeated cycling through the bullpen).
        pitcher = GameStrategy.find_closer(
            self.current_pitcher,
            self.pitch_team,
            self.inning,
            self.score_differential,
            self.rng,
        )
        if pitcher:
            outgoing = self.current_pitcher
            self._close_pitcher_appearance()
            self.current_pitcher = pitcher
            self._active_pitchers[self.pitch_team.record.id] = pitcher
            self.current_pitcher.game_stats.pitching.game_played = 1
            self.current_pitcher.current_position = "p"
            self._open_pitcher_appearance(pitcher)
            self.logger.info(f"🔒 Closer in: {self.current_pitcher.name}")
            if self.event_logger:
                self.event_logger.closer_called(
                    team_id=self.pitch_team.record.id,
                    player_id=pitcher.id,
                    name=pitcher.name,
                    outgoing_id=outgoing.id if outgoing else "",
                    outgoing_name=outgoing.name if outgoing else "",
                    score_diff=self.score_differential,
                    save_situation=GameStrategy.is_save_situation(
                        self.inning.number, self.score_differential
                    ),
                )
            return  # Don't also run the fatigue check below

        # ── Normal fatigue-based change ────────────────────────────────────
        rnd = self.rng.random()
        change = (
            GameStrategy.should_consider_pitching_change(
                self.current_pitcher,
                self.inning,
                self.score_differential,
                profile_of(self.pitch_team),
                inning_start=inning_start,
            )
            if not force
            else 1.0
        )  # injury forces the change
        if change > 0.2:
            self.logger.info(
                f"⚠️ Manager considering pitching change for {self.current_pitcher.name}"
            )
        self.logger.debug(f"Change probability: {change:.4f}")
        if self.current_pitcher.pitcher_fatigue:
            self.logger.trace(
                f"(fatigue={self.current_pitcher.pitcher_fatigue.get_level()}, runs={self.current_pitcher.game_stats.pitching.runs}, "
                f"hits={self.current_pitcher.game_stats.pitching.hits}, outs={self.current_pitcher.game_stats.pitching.outs}, pitches={self.current_pitcher.game_stats.pitching.pitch_count})"
            )
        if change > rnd and change >= 0.2:
            eligible = (
                self.home_eligible
                if self.pitch_team == self.home
                else self.away_eligible
            )
            pitcher = GameStrategy.select_relief_pitcher(
                self.pitch_team,
                self.current_pitcher,
                self.inning,
                self.score,
                pitcher_states=self.pitcher_states,
                game_date=self.game_date,
                eligible_ids=eligible,
                rng=self.rng,
            )
            if pitcher:
                outgoing = self.current_pitcher
                self._close_pitcher_appearance()
                self.current_pitcher = pitcher
                self._active_pitchers[self.pitch_team.record.id] = pitcher
                self.current_pitcher.game_stats.pitching.game_played = 1
                self.current_pitcher.current_position = "p"
                self._open_pitcher_appearance(pitcher)
                self.logger.info(f"🔄 Now pitching: {self.current_pitcher.name}")
                if self.event_logger:
                    fatigue = getattr(outgoing, "pitcher_fatigue", None)
                    level = fatigue.get_level().value if fatigue else "unknown"
                    self.event_logger.pitching_change(
                        team_id=self.pitch_team.record.id,
                        incoming_id=pitcher.id,
                        incoming_name=pitcher.name,
                        outgoing_id=outgoing.id if outgoing else "",
                        outgoing_name=outgoing.name if outgoing else "",
                        reason=f"fatigue={level}",
                        detail=f"change={change}",
                    )
            else:
                self.logger.info("⚠️ No available pitchers!")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _log_starting_lineups(self) -> None:
        """Log starting lineups and pitchers to game_events."""
        if not self.event_logger:
            return
        for team in [self.home, self.away]:
            slots = [
                {
                    "batting_order": i + 1,
                    "player_id": slot.player.id,
                    "name": slot.player.name,
                    "position": slot.position,
                }
                for i, slot in enumerate(team.lineup)
            ]
            self.event_logger.lineup_set(team_id=team.record.id, slots=slots)
            if team.pitcher:
                self.event_logger.pitcher_start(
                    team_id=team.record.id,
                    player_id=team.pitcher.id,
                    name=team.pitcher.name,
                )

    def _init_game_stats(self) -> None:
        """Initialize game stats for all players on both teams."""
        for player in self.away.players + self.home.players:
            player.init_game_stats()
        self.logger.debug("Game stats initialized for all players")

    def _sync_players(self) -> None:
        """Sync current batter and pitcher from lineups."""
        self.current_batter = self.bat_team.current_batter
        self.current_pitcher = self._active_pitchers.get(
            self.pitch_team.record.id,
            self.pitch_team.current_pitcher,  # fallback for starter
        )

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

    @property
    def score_differential(self) -> int:
        """Score differential from pitching team's perspective (positive = winning)."""
        if self.pitch_team == self.home:
            return self.score.differential
        return self.score.away - self.score.home

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
                raise GameStateError(
                    f"Plate appearances don't add up for {player.name}\n"
                    f"{PlayerTableFormatter.horizontal_stat_header()}\n"
                    f"{PlayerTableFormatter.horizontal_stats(player)}"
                )

    def check_pitcher_fatigue(self) -> FatigueLevel:
        """Check current pitcher's fatigue level."""
        if self.current_pitcher and self.current_pitcher.pitcher_fatigue:
            return self.current_pitcher.pitcher_fatigue.get_level()
        return FatigueLevel.FRESH
