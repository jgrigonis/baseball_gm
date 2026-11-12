# src/game/resolver.py

from __future__ import annotations

import logging

from src.game.bases import FIRST, SECOND, THIRD
from src.game.event import GameEvent
from src.game.events.hbp import HitByPitchEvent
from src.game.events.error import (
    FieldingErrorEvent,
    ThrowingErrorEvent,
    OutfielderThrowingErrorEvent,
    RunnerAdvancedOnErrorEvent,
)
from src.game.events.balk import BalkEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.hits import SingleEvent, DoubleEvent, TripleEvent, HomeRunEvent
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.events.sacrifice import SacBuntEvent, SacFlyEvent
from src.game.events.strike import (
    FoulStrikeEvent,
    FouledOffThirdStrikeEvent,
    FoulTipCaughtThirdStrikeEvent,
    DroppedThirdStrikeEvent,
    StrikeEvent,
)
from src.game.events.ball import BallEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import (
    OutRecordedEvent,
    GroundOutEvent,
    FlyOutEvent,
    FoulFlyOutEvent,
    LineOutEvent,
    AirDoublePlayEvent,
)
from src.game.events.double_play import DoublePlayEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent
from src.game.intents.pick_off import PickOffIntent
from src.game.resolvers.catcher_pickoff import resolve_catcher_pickoff
from src.game.resolvers.concurrent_events import resolve_concurrent_events
from src.game.modifiers.pitch_modifiers import PitchModifiers
from src.game.modifiers.in_play_modifiers import InPlayModifiers
from src.game.probabilities import (
    # Pitch outcome weights
    BALL_PROB,
    FOUL_PROB,
    HOME_RUN_PROB,
    HBP_PROB,
    BALK_PROB,
    ILLEGAL_PITCH_PROB,
    CATCHER_INTERFERENCE_PROB,
    WILD_PITCH_PROB,
    PASSED_BALL_PROB,
    IN_PLAY_PROB,
    CALLED_STRIKE_PROB,
    SWINGING_STRIKE_PROB,
    # In play outcome weights
    FLY_OUT_PROB,
    GROUND_OUT_PROB,
    SINGLE_PROB,
    DOUBLE_PROB,
    TRIPLE_PROB,
    DOUBLE_PLAY_PROB,
    FIELDERS_CHOICE_PROB,
    SAC_FLY_PROB,
    SAC_BUNT_PROB,
    TRIPLE_PLAY_PROB,
)
from src.game.resolvers.pick_off import resolve_pickoff
from src.game.resolvers.pitch import resolve_pitch
from src.game.resolvers.walk import resolve_walk
from src.util.weighted_choice import WeightedChoice


class Resolver:
    """
    Converts GameIntents into ordered GameEvents.

    Resolver must guarantee base availability before
    emitting events.

    Resolver:
    - decides outcomes
    - enforces baseball rules
    - uses randomness

    Resolver does NOT:
    - mutate game
    - apply events
    """

    def __init__(self, rng):
        self.rng = rng
        self.logger = logging.getLogger("game.resolver")

        # ============================================================
        # Initialize WeightedChoice instances
        # ============================================================
        # Main pitch outcome chooser
        self.pitch_outcome = WeightedChoice(rng=rng)
        self._setup_pitch_outcome_weights()

        # In-play outcome chooser
        self.in_play_outcome = WeightedChoice(rng=rng)
        self._setup_in_play_weights()

    # ================================================================
    # Extract weight setup into dedicated methods
    # ================================================================

    def _setup_pitch_outcome_weights(self):
        """Initialize base weights for pitch outcomes."""
        self.pitch_outcome.set_weights(
            {
                "ball": BALL_PROB,
                "foul": FOUL_PROB,
                "home_run": HOME_RUN_PROB,
                "hit_by_pitch": HBP_PROB,
                "balk": BALK_PROB,  # only with runners on base
                "illegal_pitch": ILLEGAL_PITCH_PROB,  # only with bases empty
                "catcher_interference": CATCHER_INTERFERENCE_PROB,
                "wild_pitch": WILD_PITCH_PROB,
                "passed_ball": PASSED_BALL_PROB,
                "in_play": IN_PLAY_PROB,
                "called_strike": CALLED_STRIKE_PROB,
                "swinging_strike": SWINGING_STRIKE_PROB,
            }
        )

    def _setup_in_play_weights(self):
        """Initialize base weights for in-play outcomes."""
        self.in_play_outcome.set_weights(
            {
                "fly_out": FLY_OUT_PROB,
                "ground_out": GROUND_OUT_PROB,
                "single": SINGLE_PROB,
                "double": DOUBLE_PROB,
                "triple": TRIPLE_PROB,
                "double_play": DOUBLE_PLAY_PROB,
                "fielders_choice": FIELDERS_CHOICE_PROB,
                "sac_fly": SAC_FLY_PROB,
                "sac_bunt": SAC_BUNT_PROB,
                "triple_play": TRIPLE_PLAY_PROB,
            }
        )

    def resolve(self, intent: GameIntent, game) -> list[GameEvent]:
        """
        Resolve an intent into one or more GameEvents.

        For PitchIntent, this happens in three phases:
        1. Pre-pitch phase (pickoffs, etc.)
        2. Pitch phase (pitch thrown + outcome)
        3. Concurrent phase (steals - only if ball not in play)

        Event ordering:
        - Pre-pitch events
        - Pitch thrown event
        - Pitch outcome events (balls, strikes, hits, etc.)
        - Concurrent events (steals) - BEFORE PlateAppearanceEndEvent
        - PlateAppearanceEndEvent (if applicable)
        """
        if isinstance(intent, PickOffIntent):
            return resolve_pickoff(self, intent, game)

        if isinstance(intent, PitchIntent):
            events = []
            situation = intent.pre_pitch_situation

            # Special case: intentional walk skips pitch
            if situation.intentional_walk:
                events.extend(resolve_walk(self, intent, game, intentional=True))
                return events

            # ============================================================
            # Phase 1: The pitch itself
            # ============================================================
            pitch_events = resolve_pitch(self, intent, game)

            # ============================================================
            # Phase 2: Concurrent events (steals)
            # Only process if ball was NOT put in play AND no
            # wild pitch/passed ball
            # ============================================================
            if (
                not self._ball_in_play(pitch_events)
                and not self._is_walk(pitch_events)
                and not self._is_wild_pitch_or_passed_ball(pitch_events)
                and not self._is_balk(pitch_events)
                and not self._is_foul(pitch_events)
                and not self._is_error(pitch_events)
                and not any(
                    isinstance(e, DroppedThirdStrikeEvent) for e in pitch_events
                )
            ):
                # Steals can happen on balls, strikes,
                # but not balks, walks, errors, wild pitches, passed balls, fouls or ball_in_play
                concurrent_events = resolve_concurrent_events(self, intent, game)

                # Find where the PlateAppearanceEndEvent is (if any)
                pa_end_index = self._find_pa_end_index(pitch_events)

                if pa_end_index is not None:
                    # Insert concurrent events BEFORE the PA end
                    events.extend(
                        pitch_events[:pa_end_index]
                    )  # Everything before PA end
                    events.extend(concurrent_events)  # Steal events
                    events.extend(pitch_events[pa_end_index:])  # PA end event
                else:
                    # No PA end yet (pitch didn't end PA)
                    events.extend(pitch_events)
                    events.extend(concurrent_events)
                    # A take or a swing and miss with nobody running: the
                    # catcher may throw behind a runner.
                    if not concurrent_events and self._ball_or_strike(pitch_events):
                        events.extend(resolve_catcher_pickoff(self, intent, game))
            else:
                # Ball in play - no concurrent steal events
                events.extend(pitch_events)

            return events

        raise RuntimeError(f"Unhandled intent type: {type(intent).__name__}")

    def _apply_pitch_modifiers(self, game):
        """Apply all pitch probability modifiers based on game state."""
        PitchModifiers.apply_all(self, game)

    # ================================================================
    # HELPER METHODS
    # ================================================================

    def _validate_game_state(
        self, game, require_runners=False, max_outs=None, require_runner_on=None
    ):
        """Validate game state before resolving plays"""
        if max_outs is not None and game.inning.outs >= max_outs:
            raise RuntimeError(
                f"Play cannot occur with {game.inning.outs} outs (max: {max_outs - 1})"
            )

        if require_runners and game.bases.is_empty:
            raise RuntimeError("Play cannot occur with no runners on base")

        if require_runner_on is not None:
            runner = game.bases.runner_on(require_runner_on)
            if not runner:
                base_name = {FIRST: "first", SECOND: "second", THIRD: "third"}[
                    require_runner_on
                ]
                raise RuntimeError(f"Play requires a runner on {base_name} base")

    def _find_pa_end_index(self, events: list[GameEvent]) -> int | None:
        """
        Find the index of the PlateAppearanceEndEvent in the events list.

        Args:
            events: List of events from the pitch resolution

        Returns:
            Index of PlateAppearanceEndEvent, or None if not found
        """
        for i, event in enumerate(events):
            if isinstance(event, PlateAppearanceEndEvent):
                return i
        return None

    def _inning_ended(self, events: list[GameEvent], game) -> bool:
        """
        Check if the inning ended based on the events that occurred.

        An inning ends when 3 outs are recorded (cumulative from game state
        plus new outs in these events).

        Args:
            events: List of events that occurred
            game: Current game state

        Returns:
            True if inning has ended (3 outs), False otherwise
        """
        outs_in_events = sum(1 for e in events if isinstance(e, OutRecordedEvent))
        total_outs = game.inning.outs + outs_in_events
        return total_outs >= 3

    # ================================================================
    # IN PLAY MODIFIERS
    # ================================================================

    def _apply_in_play_modifiers(self, game):
        """Apply all in-play probability modifiers."""
        InPlayModifiers.apply_all(self, game)

    # ================================================================
    # Event Checks
    # ================================================================

    def _ball_in_play(self, events: list[GameEvent]) -> bool:
        """
        Check if the ball was put in play during this pitch.

        A ball is "in play" if any of these events occurred:
        - Hits (single, double, triple, home run)
        - Outs (fly out, ground out, etc.)
        - Fielder's choice
        - Sacrifice plays
        - Double/triple plays

        Args:
            events: List of events from the pitch resolution

        Returns:
            True if ball was put in play, False otherwise
        """
        # Events that indicate ball was put in play
        in_play_event_types = (
            # Hits
            SingleEvent,
            DoubleEvent,
            TripleEvent,
            HomeRunEvent,
            # Outs
            GroundOutEvent,
            FlyOutEvent,
            LineOutEvent,
            AirDoublePlayEvent,
            # Special plays
            FieldersChoiceEvent,
            SacBuntEvent,
            SacFlyEvent,
            DoublePlayEvent,
            TriplePlayEvent,
        )

        return any(isinstance(event, in_play_event_types) for event in events)

    def _ball_or_strike(self, events: list[GameEvent]) -> bool:
        """The pitch was just a ball or a strike (taken or missed)."""
        return any(isinstance(e, (BallEvent, StrikeEvent)) for e in events)

    def _is_error(self, events: list[GameEvent]) -> bool:
        """Check if an error occurred."""
        error_event_types = (
            FieldingErrorEvent,
            ThrowingErrorEvent,
            OutfielderThrowingErrorEvent,
            RunnerAdvancedOnErrorEvent,
        )
        return any(isinstance(event, error_event_types) for event in events)

    def _is_balk(self, events: list[GameEvent]) -> bool:
        """Check if a balk occurred."""
        balk_event_types = (BalkEvent,)
        return any(isinstance(event, balk_event_types) for event in events)

    def _is_walk(self, events: list[GameEvent]) -> bool:
        """Check if a walk occurred."""
        walk_event_types = (
            WalkEvent,
            IBBEvent,
            HitByPitchEvent,
            CatcherInterferenceEvent,
        )
        return any(isinstance(event, walk_event_types) for event in events)

    def _is_wild_pitch_or_passed_ball(self, events: list[GameEvent]) -> bool:
        """Check if wild pitch or passed ball occurred."""
        return any(
            isinstance(event, (WildPitchEvent, PassedBallEvent)) for event in events
        )

    def _is_foul(self, events: list[GameEvent]) -> bool:
        """Check if a foul ball occurred."""
        foul_event_types = (
            FoulStrikeEvent,
            FouledOffThirdStrikeEvent,
            FoulTipCaughtThirdStrikeEvent,
            FoulFlyOutEvent,
        )
        return any(isinstance(event, foul_event_types) for event in events)

    # ================================================================
    # Pitch outcome determination
    # ================================================================
    def determine_pitch_outcome(self, intent, game) -> str:
        """
        Determine pitch outcome. Override point for testing.

        Default implementation uses weighted random selection based on:
        - Base state (runners on base)
        - Game situation (bunt attempt, hit-and-run, etc.)
        - Count
        - Batter and pitcher skills

        Returns one of: ball, called_strike, swinging_strike, foul, hit_by_pitch, catcher_interference,
                        illegal_pitch, balk, wild_pitch, passed_ball, home_run, in_play
        """
        self.pitch_outcome.reset()
        self._apply_pitch_modifiers(game)
        return self.pitch_outcome.choose()
