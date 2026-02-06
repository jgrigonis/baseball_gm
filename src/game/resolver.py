# src/game/resolver.py

from __future__ import annotations

import logging
from typing import List

from src.game.bases import FIRST, SECOND, THIRD, HOME, Bases
from src.game.count import Count
from src.game.score import Score
from src.game.event import GameEvent
from src.game.events.ball import BallEvent, IllegalPitch
from src.game.events.hbp import HitByPitchEvent
from src.game.events.error import FieldingErrorEvent, ThrowingErrorEvent
from src.game.events.noop import NoOpEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.events.balk import BalkEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.hits import SingleEvent, DoubleEvent, TripleEvent, HomeRunEvent
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent
from src.game.events.sacrifice import SacBuntEvent, SacFlyEvent
from src.game.events.steal import (
    StealAttemptEvent,
    StolenBaseEvent,
    CaughtStealingEvent,
    DoubleStealAttemptEvent,
)
from src.game.events.strike import (
    StrikeEvent,
    FoulStrikeEvent,
    FouledOffThirdStrikeEvent,
    FoulTipCaughtThirdStrikeEvent,
)
from src.game.events.strikeout import StrikeOutEvent
from src.game.events.pick_off import (
    PickoffAttemptEvent,
    PickoffSuccessEvent,
    PickoffFailedEvent,
    PickoffErrorEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import (
    OutRecordedEvent,
    GroundOutEvent,
    FlyOutEvent,
    FoulFlyOutEvent,
    PutOutEvent,
)
from src.game.events.double_play import DoublePlayEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent, PrePitchSituation
from src.game.intents.pick_off import PickOffIntent
from src.game.rules.force_advancement import force_advance_chain
from src.game.strategy import GameStrategy
from src.player.player_in_game import PlayerInGame
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

    # Probability thresholds
    FOUL_TIP_CAUGHT_PROB = 0.05
    FOUL_FLY_OUT_WITH_TWO_STRIKES_PROB = 0.05
    FOUL_FLY_OUT_BEFORE_TWO_STRIKES_PROB = 0.05
    FOULED_OFF_THIRD_STRIKE_PROB = 0.95

    # Triple play random selection boundaries
    TRIPLE_PLAY_FIRST_SECOND_THRESHOLD = 0.3333
    TRIPLE_PLAY_FIRST_THIRD_THRESHOLD = 0.6666

    # Default tag up chances
    PROB_TAGUP_FROM_SECOND_FLYOUT = 0.7
    PROB_TAGUP_FROM_FIRST_FLYOUT = 0.3

    # Base advancement probabilities
    SCORE_FROM_SECOND_ON_SINGLE = 0.60  # 60% chance runner scores from 2nd
    FIRST_TO_THIRD_ON_SINGLE = 0.35  # 35% chance runner goes 1st to 3rd
    SCORE_FROM_FIRST_ON_DOUBLE = 0.21  # 21%
    FIRST_TO_HOME_ON_SINGLE = 0.03

    # Probability constants for events
    PICKOFF_SUCCESS_PROB = 0.15  # 15% successful
    PICKOFF_ERROR_PROB = 0.05  # 5% throwing error

    STEAL_SECOND_SUCCESS_PROB = 0.75  # 75% success rate
    STEAL_THIRD_SUCCESS_PROB = 0.60  # 60% success rate
    STEAL_HOME_SUCCESS_PROB = 0.05  # 5% success rate

    STEAL_ON_PICKOFF_MODIFIER = 1.5

    BASE_ERROR_RATE = 0.025

    BASE_THROWOUT_PROB = 0.05

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

        self.infielder_bunt_choice = WeightedChoice(
            {
                "shortstop": 2,
                "second_baseman": 2,
                "third_baseman": 20,
                "pitcher": 15,
                "catcher": 20,
            }
        )
        # Infielder selection chooser
        self.infielder_choice = WeightedChoice(
            {
                "shortstop": 32,
                "second_baseman": 25,
                "third_baseman": 20,
                "first_baseman": 18,
                "pitcher": 5,
            },
            rng=rng,
        )

        # Outfielder selection chooser
        self.outfielder_choice = WeightedChoice(
            {
                "center_fielder": 39,
                "right_fielder": 32,
                "left_fielder": 29,
            },
            rng=rng,
        )

        self.foul_fly_choice = WeightedChoice(
            {
                "right_fielder": 32,
                "left_fielder": 30,
                "first_baseman": 9,
                "third_baseman": 9,
                "second_baseman": 4,
                "shortstop": 4,
                "catcher": 4,
                "pitcher": 2,
            },
            rng=rng,
        )

        self.double_play_choice = WeightedChoice(
            {
                "6-4-3": 43,
                "4-6-3": 23,
                "5-4-3": 12,
                "3-6-3": 7,
                "6-3": 4,
                "3-6": 3,
                "4-3": 2,
                "1-6-3": 2,
                "3-6-1": 2,
            },
            rng=rng,
        )

        self._3to1_dp_choice = WeightedChoice(
            {
                "5-2-3": 18,
                "6-2-3": 25,
                "4-2-3": 22,
                "1-2-3": 12,
                "3-2-3": 12,
                "5-5": 4,
                "6-5": 3,
            },
            rng=rng,
        )

        self._2to1_dp_choice = WeightedChoice(
            {
                "6-3": 25,
                "6-5-3": 25,
                "5-3": 25,
                "4-6": 25,
            }
        )

    def set_rng(self, rng):
        """Set RNG for resolver and all weighted choices."""
        self.rng = rng
        self.pitch_outcome.rng = rng
        self.in_play_outcome.rng = rng
        self.infielder_choice.rng = rng
        self.outfielder_choice.rng = rng

    # ================================================================
    # Extract weight setup into dedicated methods
    # ================================================================

    def _setup_pitch_outcome_weights(self):
        """Initialize base weights for pitch outcomes."""
        self.pitch_outcome.set_weights(
            {
                "ball": 10800,
                "foul": 5100,
                "home_run": 280,
                "hit_by_pitch": 60,
                "balk": 0,  # only with runners on base
                "illegal_pitch": 0,  # only with bases empty
                "catcher_interference": 10,
                "wild_pitch": 10,
                "passed_ball": 10,
                "in_play": 5855,
                "strike": 7100,  # TODO replace with called_strike and swinging_strike
            }
        )

    def _setup_in_play_weights(self):
        """Initialize base weights for in-play outcomes."""
        self.in_play_outcome.set_weights(
            {
                "fly_out": 2050,
                "ground_out": 2050,
                "single": 1350,
                "double": 360,
                "triple": 45,
                "double_play": 0,
                "fielders_choice": 0,
                "sac_fly": 0,
                "sac_bunt": 0,
                "triple_play": 0,
            }
        )

    def resolve(self, intent: GameIntent, game) -> List[GameEvent]:
        """
        Resolve an intent into one or more GameEvents.

        Must always return at least one event.
        """
        if isinstance(intent, PitchIntent):
            return self._resolve_pitch(intent, game)

        raise RuntimeError(f"Unhandled intent type: {type(intent).__name__}")

    def _resolve_pitch(self, intent: PitchIntent, game) -> List[GameEvent]:
        events: List[GameEvent] = []

        # ------------------------------------------------------------
        # 1. Pitch is always thrown
        # ------------------------------------------------------------
        events.append(
            PitchThrownEvent(
                pitcher=intent.pitcher,
                batter=intent.batter,
                count=game.count.snapshot(),
                # pitch_type=intent.pitch_type,
            )
        )

        # ------------------------------------------------------------
        # 2. Determine outcome (pure decision)
        # ------------------------------------------------------------
        outcome = self._determine_pitch_outcome(intent, game)
        self.logger.trace(outcome)

        # Sanity check
        assert outcome in (
            "ball",
            "strike",
            "called_strike",
            "swinging_strike",
            "foul",
            "hit_by_pitch",
            "catcher_interference",
            "illegal_pitch",
            "balk",
            "wild_pitch",
            "passed_ball",
            "home_run",
            "in_play",
        )

        # ------------------------------------------------------------
        # 3. Emit outcome specific events
        # ------------------------------------------------------------
        if outcome == "in_play":
            self.logger.trace("outcome is in_play")
            events.extend(self._resolve_ball_in_play(intent, game))

        elif outcome == "ball":
            events.extend(self._handle_ball(intent, game))

        elif outcome in ("strike", "called_strike", "swinging_strike"):
            events.extend(self._handle_strike_outcome(outcome, intent, game))

        elif outcome == "foul":
            events.extend(self._resolve_foul(intent, game))

        elif outcome == "hit_by_pitch":
            events.extend(self._resolve_walk(intent, game, hbp=True))

        elif outcome == "catcher_interference":
            events.extend(self._resolve_walk(intent, game, catcher_interference=True))

        elif outcome == "illegal_pitch":
            events.extend(self._handle_illegal_pitch(intent, game))

        elif outcome == "balk":
            events.extend(self._handle_balk(game))

        elif outcome == "wild_pitch":
            events.extend(self._handle_wild_pitch(intent, game))

        elif outcome == "passed_ball":
            events.extend(self._handle_passed_ball(intent, game))

        elif outcome == "home_run":
            self.logger.trace("home_run")
            events.extend(self._resolve_home_run(intent, game))

        else:
            return [NoOpEvent()]

        self.logger.trace(f"events = {events}")
        return events

    def _determine_pitch_outcome(self, intent, game) -> str:
        """
        Decide the immediate result of a pitch.

        Must:
        - be pure (no mutation)
        - use rng only
        - return one of a small fixed set of strings

        Extremely simple pitch outcome model.

        This will be replaced later with real models.
        """
        self.logger.trace("_determine_pitch_outcome")

        # Reset to base weights
        self.pitch_outcome.reset()

        # Apply all modifiers
        self._apply_pitch_modifiers(game)

        # Make the choice
        return self.pitch_outcome.choose()

    def _apply_pitch_modifiers(self, game):
        """Apply all pitch probability modifiers based on game state."""
        self._modify_for_bases(game.bases)
        self._modify_for_situation(game.situation, game.current_batter.player)
        self._modify_for_count(game.count)
        self._modify_for_batter(game.current_batter.player)
        self._modify_for_pitcher(game.current_pitcher)

    def _modify_for_bases(self, bases: Bases):
        """
        Modify probabilities based on base state.

        BEFORE: Direct dict manipulation
        AFTER: Use multiply(), set() methods
        """
        if bases.is_empty:
            self.pitch_outcome.set("illegal_pitch", 10)
        else:
            self.pitch_outcome.set("balk", 10)
            self.pitch_outcome.multiply("ball", 1.03)
            self.pitch_outcome.multiply("strike", 0.97)
            self.pitch_outcome.multiply("foul", 0.94)
            self.pitch_outcome.multiply("in_play", 1.18)
            self.pitch_outcome.multiply("home_run", 1.18)

    def _modify_for_situation(self, situation: PrePitchSituation, batter: PlayerInGame):
        """Modify probabilities based on game situation."""
        bunting = batter.skills["bunting"]
        contact = batter.skills["contact"]

        if situation.bunt_attempt:
            self.pitch_outcome.add("strike", -25 * bunting)
            self.pitch_outcome.add("foul", 25 * (100 - bunting))
            self.pitch_outcome.set("home_run", 0)
            self.pitch_outcome.add("in_play", 25 * (100 - bunting))

        if situation.hit_and_run:
            self.pitch_outcome.add("strike", -90 * contact)
            self.pitch_outcome.set("ball", 10)
            self.pitch_outcome.add("foul", 4 * (100 - contact))
            self.pitch_outcome.add("home_run", 2 * (contact - 60))
            self.pitch_outcome.multiply("balk", 1.2)
            self.pitch_outcome.multiply("catcher_interference", 1.2)
            self.pitch_outcome.add("in_play", 90 * contact)

        if situation.pitch_out:
            self.pitch_outcome.multiply("strike", 0.05)
            self.pitch_outcome.multiply("ball", 2.0)
            self.pitch_outcome.multiply("foul", 0.05)
            self.pitch_outcome.multiply("home_run", 0.01)
            self.pitch_outcome.multiply("hit_by_pitch", 0.01)
            self.pitch_outcome.multiply("catcher_interference", 1.2)
            self.pitch_outcome.multiply("wild_pitch", 0.05)
            self.pitch_outcome.multiply("in_play", 0.001)

        if situation.hit_and_run and situation.pitch_out:
            self.pitch_outcome.multiply("strike", 25)
            self.pitch_outcome.multiply("foul", 10)
            self.pitch_outcome.multiply("in_play", 50)

    def _modify_for_count(self, count: Count):
        """
        Modify probabilities based on count.

        Could be further refactored into a lookup table.
        """
        if count.balls == 0 and count.strikes == 0:
            self.pitch_outcome.multiply("ball", 1.15)
            self.pitch_outcome.multiply("strike", 1.33)
            self.pitch_outcome.multiply("foul", 0.66)
            self.pitch_outcome.multiply("home_run", 0.61)
            self.pitch_outcome.multiply("in_play", 0.66)
        elif count.balls == 1 and count.strikes == 0:
            self.pitch_outcome.multiply("ball", 0.92)
            self.pitch_outcome.multiply("strike", 1.12)
            self.pitch_outcome.multiply("foul", 0.94)
            self.pitch_outcome.multiply("home_run", 1.1)
            self.pitch_outcome.multiply("in_play", 1.1)
        elif count.balls == 0 and count.strikes == 1:
            self.pitch_outcome.multiply("ball", 1.13)
            self.pitch_outcome.multiply("strike", 0.74)
            self.pitch_outcome.multiply("foul", 1.11)
            self.pitch_outcome.multiply("home_run", 0.78)
            self.pitch_outcome.multiply("in_play", 0.84)
        elif count.balls == 2 and count.strikes == 0:
            self.pitch_outcome.multiply("ball", 1.08)
            self.pitch_outcome.multiply("strike", 1.44)
            self.pitch_outcome.multiply("foul", 0.57)
            self.pitch_outcome.multiply("home_run", 0.69)
            self.pitch_outcome.multiply("in_play", 0.7)
        elif count.balls == 1 and count.strikes == 1:
            self.pitch_outcome.multiply("ball", 0.96)
            self.pitch_outcome.multiply("strike", 0.78)
            self.pitch_outcome.multiply("foul", 1.34)
            self.pitch_outcome.multiply("home_run", 1.15)
            self.pitch_outcome.multiply("in_play", 1.1)
        elif count.balls == 0 and count.strikes == 2:
            self.pitch_outcome.multiply("ball", 1.37)
            self.pitch_outcome.multiply("strike", 0.6)
            self.pitch_outcome.multiply("foul", 1.02)
            self.pitch_outcome.multiply("home_run", 0.74)
            self.pitch_outcome.multiply("in_play", 0.77)
        elif count.balls == 3 and count.strikes == 0:
            self.pitch_outcome.multiply("ball", 0.89)
            self.pitch_outcome.multiply("strike", 2.56)
            self.pitch_outcome.multiply("foul", 0.08)
            self.pitch_outcome.multiply("home_run", 0.21)
            self.pitch_outcome.multiply("in_play", 0.2)
        elif count.balls == 2 and count.strikes == 1:
            self.pitch_outcome.multiply("ball", 0.69)
            self.pitch_outcome.multiply("strike", 0.89)
            self.pitch_outcome.multiply("foul", 1.19)
            self.pitch_outcome.multiply("home_run", 1.71)
            self.pitch_outcome.multiply("in_play", 1.64)
        elif count.balls == 1 and count.strikes == 2:
            self.pitch_outcome.multiply("ball", 0.97)
            self.pitch_outcome.multiply("strike", 0.71)
            self.pitch_outcome.multiply("foul", 1.26)
            self.pitch_outcome.multiply("home_run", 1.16)
            self.pitch_outcome.multiply("in_play", 1.17)
        elif count.balls == 3 and count.strikes == 1:
            self.pitch_outcome.multiply("ball", 0.95)
            self.pitch_outcome.multiply("strike", 0.76)
            self.pitch_outcome.multiply("foul", 0.79)
            self.pitch_outcome.multiply("home_run", 1.57)
            self.pitch_outcome.multiply("in_play", 1.56)
        elif count.balls == 2 and count.strikes == 2:
            self.pitch_outcome.multiply("ball", 0.65)
            self.pitch_outcome.multiply("strike", 0.76)
            self.pitch_outcome.multiply("foul", 1.54)
            self.pitch_outcome.multiply("home_run", 1.63)
            self.pitch_outcome.multiply("in_play", 1.51)
        elif count.balls == 3 and count.strikes == 2:
            self.pitch_outcome.multiply("ball", 0.62)
            self.pitch_outcome.multiply("strike", 0.65)
            self.pitch_outcome.multiply("foul", 1.36)
            self.pitch_outcome.multiply("home_run", 1.66)
            self.pitch_outcome.multiply("in_play", 1.72)

    def _modify_for_batter(self, batter: PlayerInGame):
        """Modify probabilities based on batter skills."""
        eye = batter.skills["eye"]
        self.pitch_outcome.add("strike", -8 * (eye - 50))
        self.pitch_outcome.add("foul", 4 * (eye - 50))
        self.pitch_outcome.add("ball", 4 * (eye - 50))

        contact = batter.skills["contact"]
        self.pitch_outcome.add("strike", -4 * (contact - 50))
        self.pitch_outcome.add("foul", int(1.2 * (contact - 50)))
        self.pitch_outcome.add("in_play", int(1.5 * (contact - 50)))

    def _modify_for_pitcher(self, pitcher: PlayerInGame):
        """Modify probabilities based on pitcher skills."""
        accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
        self.pitch_outcome.add("ball", -20 * (accuracy - 50))
        self.pitch_outcome.add("strike", 15 * (accuracy - 50))
        self.pitch_outcome.add("hit_by_pitch", -(accuracy - 50))

        # Only modify if non-zero
        self.pitch_outcome.add("wild_pitch", -(accuracy - 50))
        self.pitch_outcome.add("passed_ball", int(-0.5 * (accuracy - 50)))

        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])

        self.pitch_outcome.add("home_run", -(ground_balls - 40))

        strikes = pitcher.get_effective_stat(pitcher.skills["strikes"])

        self.pitch_outcome.add("ball", -10 * (strikes - 50))
        self.pitch_outcome.add("strike", 20 * (strikes - 50))
        self.pitch_outcome.add("foul", 2 * (strikes - 50))

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

    def _advance_all_runners(
        self, game, bases: tuple, advancement: int, reason: str, rbi_batter=None
    ) -> list[GameEvent]:
        """Advance runners on specified bases by advancement amount (capped at HOME)"""
        events = []
        for base in bases:
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=base,
                    to_base=min(base + advancement, HOME),
                    reason=reason,
                    rbi_batter=rbi_batter,
                    pitcher=game.current_pitcher,
                )
            )
        return events

    def _advance_batter_to_base(
        self, batter: str, pitcher: str, to_base: int, reason: str
    ) -> RunnerAdvancedEvent:
        """Create event for batter advancing to a base"""
        return RunnerAdvancedEvent(
            runner=batter,
            from_base=None,
            to_base=to_base,
            reason=reason,
            pitcher=pitcher,
        )

    def _handle_ball(self, intent, game) -> list[GameEvent]:
        """Handle a ball being called"""
        events = [BallEvent()]
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game))
        return events

    def _handle_strike_outcome(
        self, outcome: str, intent: PitchIntent, game
    ) -> list[GameEvent]:
        """Handle different types of strikes"""
        events = []

        if outcome == "strike":
            events.append(StrikeEvent())
        elif outcome == "called_strike":
            events.append(StrikeEvent(swinging=False))
        elif outcome == "swinging_strike":
            events.append(StrikeEvent(swinging=True))

        # Check for strikeout
        if game.count.strikes + 1 >= 3:
            self.logger.debug("strike out ending pa")
            events.extend(
                [
                    StrikeOutEvent(batter=intent.batter, pitcher=intent.pitcher),
                    PutOutEvent(game.pitch_team.current_catcher),
                    OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher),
                    PlateAppearanceEndEvent(reason="strikeout", batter=intent.batter),
                ]
            )

        return events

    def _handle_illegal_pitch(self, intent, game) -> list[GameEvent]:
        """Handle an illegal pitch"""
        events = [IllegalPitch(pitcher=intent.pitcher), BallEvent()]
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game))
        return events

    def _handle_balk(self, game) -> list[GameEvent]:
        """Handle a balk"""
        if game.bases.is_empty:
            self.logger.trace("Balk called with no runners on.")
            return []
        return [BalkEvent(pitcher=game.current_pitcher)]

    def _handle_wild_pitch(self, intent, game) -> list[GameEvent]:
        """Handle a wild pitch"""
        events = []
        # Always add the ball
        events.append(BallEvent())

        # Add wild pitch event if runners on (BEFORE walk logic)
        if not game.bases.is_empty:
            events.append(WildPitchEvent(pitcher=game.current_pitcher))
        else:
            self.logger.trace("Wild Pitch occurred with no runners on.")

        # Check for walk
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game, skip_force_advance=True))
        return events

    def _handle_passed_ball(self, intent, game) -> list[GameEvent]:
        """Handle a passed ball"""
        events = []
        # Always add the ball
        events.append(BallEvent())

        # Add passed ball event if runners on (BEFORE walk logic)
        if not game.bases.is_empty:
            events.append(
                PassedBallEvent(
                    catcher=game.pitch_team.current_catcher,
                    pitcher=game.current_pitcher,
                )
            )
        else:
            self.logger.trace("Passed Ball occurred with no runners on.")

        # Check for walk
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game, skip_force_advance=True))
        return events

    def _ball_in_play(self, events: List[GameEvent]) -> bool:
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
            # Special plays
            FieldersChoiceEvent,
            SacBuntEvent,
            SacFlyEvent,
            DoublePlayEvent,
            TriplePlayEvent,
        )

        return any(isinstance(event, in_play_event_types) for event in events)

    def _find_pa_end_index(self, events: List[GameEvent]) -> int | None:
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

    def _inning_ended(self, events: List[GameEvent], game) -> bool:
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
    # BALL IN PLAY RESOLUTION
    # ================================================================

    def _resolve_ball_in_play(self, intent, game, foul=False) -> list[GameEvent]:
        """
        Resolve a ball put into play.

        Must:
        - use rng
        - not mutate game
        - return concrete events
        """
        # Reset to base weights
        self.in_play_outcome.reset()

        # Apply all modifiers
        self._apply_in_play_modifiers(game)

        # Make the choice
        outcome = self.in_play_outcome.choose()

        # Mapping approach for cleaner dispatch
        outcome_handlers = {
            "fly_out": self._resolve_fly_out,
            "ground_out": self._resolve_ground_out,
            "single": self._resolve_single,
            "double": self._resolve_double,
            "triple": self._resolve_triple,
            "double_play": self._resolve_double_play,
            "fielders_choice": self._resolve_fielders_choice,
            "sac_fly": self._resolve_sac_fly,
            "sac_bunt": self._resolve_sac_bunt,
            "triple_play": self._resolve_triple_play,
        }
        self.logger.trace(f"in_play_outcome = {outcome}")
        if outcome in outcome_handlers:
            return outcome_handlers[outcome](intent, game)

        raise RuntimeError(f"Unknown in-play outcome: {outcome}")

    def _apply_in_play_modifiers(self, game):
        """Apply all in-play probability modifiers."""
        self._modify_in_play_for_bases_outs(game.bases, game.inning.outs)
        self._modify_in_play_for_situation(game.situation, game.current_batter.player)
        self._modify_in_play_for_count(game.count)
        self._modify_in_play_for_batter(game.current_batter.player, game.score)
        self._modify_in_play_for_pitcher(game.current_pitcher, game.score)
        self._modify_in_play_for_defense(game)
        self._modify_in_play_for_infield_defense(game)
        self._apply_in_play_constraints(game.bases, game.inning.outs)

    def _modify_in_play_for_bases_outs(self, bases: Bases, outs: int):
        """Modify in-play probabilities based on bases and outs."""
        if bases.runner_on(THIRD) and outs < 2:
            self.in_play_outcome.set("sac_fly", 1400)
            self.in_play_outcome.set("fly_out", 650)
        if bases.runner_on(FIRST) and bases.runner_on(SECOND) and outs == 0:
            self.in_play_outcome.set("triple_play", 10)
        if bases.runner_on(FIRST) and bases.runner_on(THIRD) and outs == 0:
            self.in_play_outcome.set("triple_play", 2)
        if bases.runner_on(SECOND) and bases.runner_on(THIRD) and outs == 0:
            self.in_play_outcome.set("triple_play", 2)
        if bases.runner_on(FIRST) and outs < 2:
            self.in_play_outcome.set("double_play", 400)
            self.in_play_outcome.multiply("ground_out", 0.5)
            self.in_play_outcome.set("fielders_choice", 1950)

    def _modify_in_play_for_situation(
        self, situation: PrePitchSituation, batter: PlayerInGame
    ):
        """Modify in-play probabilities based on situation."""
        bunting = batter.skills["bunting"]

        if situation.bunt_attempt:
            self.in_play_outcome.add("fly_out", -15 * bunting)
            self.in_play_outcome.add("ground_out", 2 * (100 - bunting))
            self.in_play_outcome.multiply("single", 0.08)
            self.in_play_outcome.set("double", 0)
            self.in_play_outcome.set("triple", 0)
            self.in_play_outcome.add("double_play", 50 - bunting)
            self.in_play_outcome.add("fielders_choice", -3 * bunting)
            self.in_play_outcome.set("sac_bunt", 2000)
            self.in_play_outcome.set("sac_fly", 0)

        if situation.double_steal_attempt:
            self.in_play_outcome.multiply("double_play", 0.5)
            self.in_play_outcome.multiply("fielders_choice", 0.5)
            self.in_play_outcome.multiply("ground_out", 2.0)
            self.in_play_outcome.multiply("triple_play", 0.5)

        if situation.hit_and_run:
            self.in_play_outcome.multiply("ground_out", 2.0)
            self.in_play_outcome.multiply("double_play", 0.5)
            self.in_play_outcome.multiply("fielders_choice", 0.5)
            self.in_play_outcome.multiply("triple_play", 0.5)

        if situation.steal_attempt:
            self.in_play_outcome.multiply("ground_out", 2.0)
            self.in_play_outcome.multiply("double_play", 0.5)
            self.in_play_outcome.multiply("fielders_choice", 0.5)
            self.in_play_outcome.multiply("triple_play", 0.5)

    def _modify_in_play_for_count(self, count: Count):
        """Modify the probabilities based on the count."""
        if count.balls == 0 and count.strikes == 0:
            self.in_play_outcome.multiply("fly_out", 0.66)
            self.in_play_outcome.multiply("ground_out", 0.66)
            self.in_play_outcome.multiply("single", 0.61)
            self.in_play_outcome.multiply("double", 0.61)
            self.in_play_outcome.multiply("triple", 0.61)
        elif count.balls == 1 and count.strikes == 0:
            self.in_play_outcome.multiply("fly_out", 1.01)
            self.in_play_outcome.multiply("ground_out", 1.01)
            self.in_play_outcome.multiply("single", 1.1)
            self.in_play_outcome.multiply("double", 1.1)
            self.in_play_outcome.multiply("triple", 1.1)
        elif count.balls == 0 and count.strikes == 1:
            self.in_play_outcome.multiply("fly_out", 1.08)
            self.in_play_outcome.multiply("ground_out", 1.08)
            self.in_play_outcome.multiply("single", 0.78)
            self.in_play_outcome.multiply("double", 0.78)
            self.in_play_outcome.multiply("triple", 0.78)
        elif count.balls == 2 and count.strikes == 0:
            self.in_play_outcome.multiply("fly_out", 0.72)
            self.in_play_outcome.multiply("ground_out", 0.72)
            self.in_play_outcome.multiply("single", 0.69)
            self.in_play_outcome.multiply("double", 0.69)
            self.in_play_outcome.multiply("triple", 0.69)
        elif count.balls == 1 and count.strikes == 1:
            self.in_play_outcome.multiply("fly_out", 1.01)
            self.in_play_outcome.multiply("ground_out", 1.01)
            self.in_play_outcome.multiply("single", 1.15)
            self.in_play_outcome.multiply("double", 1.15)
            self.in_play_outcome.multiply("triple", 1.15)
        elif count.balls == 0 and count.strikes == 2:
            self.in_play_outcome.multiply("fly_out", 0.82)
            self.in_play_outcome.multiply("ground_out", 0.82)
            self.in_play_outcome.multiply("single", 0.74)
            self.in_play_outcome.multiply("double", 0.74)
            self.in_play_outcome.multiply("triple", 0.74)
        elif count.balls == 3 and count.strikes == 0:
            self.in_play_outcome.multiply("fly_out", 0.09)
            self.in_play_outcome.multiply("ground_out", 0.09)
            self.in_play_outcome.multiply("single", 0.21)
            self.in_play_outcome.multiply("double", 0.21)
            self.in_play_outcome.multiply("triple", 0.21)
        elif count.balls == 2 and count.strikes == 1:
            self.in_play_outcome.multiply("fly_out", 1.47)
            self.in_play_outcome.multiply("ground_out", 1.47)
            self.in_play_outcome.multiply("single", 1.71)
            self.in_play_outcome.multiply("double", 1.71)
            self.in_play_outcome.multiply("triple", 1.71)
        elif count.balls == 1 and count.strikes == 2:
            self.in_play_outcome.multiply("fly_out", 1.2)
            self.in_play_outcome.multiply("ground_out", 1.2)
            self.in_play_outcome.multiply("single", 1.16)
            self.in_play_outcome.multiply("double", 1.16)
            self.in_play_outcome.multiply("triple", 1.16)
        elif count.balls == 3 and count.strikes == 1:
            self.in_play_outcome.multiply("fly_out", 1.56)
            self.in_play_outcome.multiply("ground_out", 1.56)
            self.in_play_outcome.multiply("single", 1.57)
            self.in_play_outcome.multiply("double", 1.57)
            self.in_play_outcome.multiply("triple", 1.57)
        elif count.balls == 2 and count.strikes == 2:
            self.in_play_outcome.multiply("fly_out", 1.39)
            self.in_play_outcome.multiply("ground_out", 1.39)
            self.in_play_outcome.multiply("single", 1.63)
            self.in_play_outcome.multiply("double", 1.63)
            self.in_play_outcome.multiply("triple", 1.63)
        elif count.balls == 3 and count.strikes == 2:
            self.in_play_outcome.multiply("fly_out", 1.88)
            self.in_play_outcome.multiply("ground_out", 1.88)
            self.in_play_outcome.multiply("single", 1.66)
            self.in_play_outcome.multiply("double", 1.66)
            self.in_play_outcome.multiply("triple", 1.66)

    def _modify_in_play_for_batter(self, batter: PlayerInGame, score: Score):
        """Modify the probabilities based on the batter skills."""
        # power
        power = batter.skills["power"]
        self.in_play_outcome.add("fly_out", -4 * (power - 50))
        self.in_play_outcome.add("single", -1 * (power - 50))
        self.in_play_outcome.add("double", (power - 50))
        contact = batter.skills["contact"]
        self.in_play_outcome.add("single", 2 * (contact - 50))
        self.in_play_outcome.add("ground_out", (contact - 50))
        # speed
        speed = batter.skills["speed"]
        self.in_play_outcome.add("ground_out", -1 * (speed - 50))
        self.in_play_outcome.add("single", 0.9 * (speed - 50))
        self.in_play_outcome.add("double", 0.1 * (speed - 50))
        self.in_play_outcome.add("triple", 0.1 * (speed - 50))
        self.in_play_outcome.add("double_play", -1 * (speed - 50))
        self.in_play_outcome.add("fielders_choice", (speed - 50))
        clutch = batter.skills["clutch"]
        if -2 < score.differential < 2:
            self.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            self.in_play_outcome.add("ground_out", 2 * (clutch - 50))
            self.in_play_outcome.add("single", (clutch - 50))
            self.in_play_outcome.add("double", 0.5 * (clutch - 50))

    def _modify_in_play_for_pitcher(self, pitcher: PlayerInGame, score: Score):
        """Modify the probabilities based on pitcher skills."""
        # ground_balls
        ground_balls = pitcher.get_effective_stat(pitcher.skills["ground_balls"])
        # changes ground_out, double_play, fielders_choice, sac_fly, triple_play
        self.in_play_outcome.add("ground_out", 4 * ground_balls)
        self.in_play_outcome.add("double_play", 0.8 * ground_balls)
        self.in_play_outcome.add("fielders_choice", 0.5 * ground_balls)
        self.in_play_outcome.add("sac_fly", -0.5 * (ground_balls - 50))

        # clutch
        clutch = pitcher.skills["clutch"]
        if -2 < score.differential < 2:
            self.in_play_outcome.add("fly_out", 2 * (clutch - 50))
            self.in_play_outcome.add("ground_out", 2 * (clutch - 50))
            self.in_play_outcome.add("single", 50 - clutch)
            self.in_play_outcome.add("double", 0.5 * (50 - clutch))

    def _modify_in_play_for_defense(self, game):
        """Modify hit probabilities based on defensive positioning"""
        # Average outfield range
        lf_range = int(
            (
                game.pitch_team.current_left_fielder.skills["speed"]
                + game.pitch_team.current_left_fielder.skills["outfield"]
            )
            / 2
        )
        cf_range = int(
            (
                game.pitch_team.current_center_fielder.skills["speed"]
                + game.pitch_team.current_center_fielder.skills["outfield"]
            )
            / 2
        )
        rf_range = int(
            (
                game.pitch_team.current_right_fielder.skills["speed"]
                + game.pitch_team.current_right_fielder.skills["outfield"]
            )
            / 2
        )
        avg_of_range = (lf_range + cf_range + rf_range) / 3

        # Better range = more outs, fewer hits
        range_factor = 50 / max(1, avg_of_range)
        self.in_play_outcome.multiply("fly_out", range_factor)
        self.in_play_outcome.multiply("single", 1 / range_factor)
        self.in_play_outcome.multiply("double", 1 / range_factor)
        self.in_play_outcome.multiply("triple", 1 / (range_factor * 1.5))

    def _modify_in_play_for_infield_defense(self, game):
        """Modify probabilities based on infield defensive skills"""
        # Average infield skill
        ss_skill = (
            game.pitch_team.current_shortstop.skills["infield"]
            + game.pitch_team.current_shortstop.skills["arm"]
        )
        _2b_skill = (
            game.pitch_team.current_second_baseman.skills["infield"]
            + game.pitch_team.current_second_baseman.skills["arm"]
        )
        _3b_skill = (
            game.pitch_team.current_third_baseman.skills["infield"]
            + game.pitch_team.current_third_baseman.skills["arm"]
        )
        _1b_skill = game.pitch_team.current_first_baseman.skills["infield"]

        avg_if_skill = (2 * ss_skill + 2 * _2b_skill + _3b_skill + _1b_skill) / 9

        # Better infield defense
        defense_factor = avg_if_skill / 50

        # Increases double play probability
        self.in_play_outcome.multiply("double_play", defense_factor)
        # Decreases errors/fielders choices
        self.in_play_outcome.multiply("fielders_choice", 1 / defense_factor)
        # Slightly increases ground outs
        self.in_play_outcome.multiply("ground_out", defense_factor * 1.1)

    def _apply_in_play_constraints(self, bases: Bases, outs: int):
        """
        Apply final constraints to ensure probabilities are valid.

        This is cleaner than the original because we can just set to 0.
        """
        if bases.number_of_baserunners < 2:
            self.in_play_outcome.set("triple_play", 0)

        if bases.number_of_baserunners < 1:
            self.in_play_outcome.set("double_play", 0)
            self.in_play_outcome.set("fielders_choice", 0)
            self.in_play_outcome.set("sac_fly", 0)
            self.in_play_outcome.set("sac_bunt", 0)

        if not bases.runner_on(THIRD):
            self.in_play_outcome.set("sac_fly", 0)

        if outs > 0:
            self.in_play_outcome.set("triple_play", 0)

        if outs > 1:
            self.in_play_outcome.set("double_play", 0)
            self.in_play_outcome.set("fielders_choice", 0)
            self.in_play_outcome.set("sac_fly", 0)
            self.in_play_outcome.set("sac_bunt", 0)

    def _resolve_fly_out(self, intent, game) -> list[GameEvent]:
        """Resolve a fly out"""
        events = []
        lf_arm = game.pitch_team.current_left_fielder.skills["arm"]
        cf_arm = game.pitch_team.current_center_fielder.skills["arm"]
        rf_arm = game.pitch_team.current_right_fielder.skills["arm"]
        arm = self.rng.choice([lf_arm, cf_arm, rf_arm])

        tag_from_second, tag_from_first = self.adjust_tagup_probs(game.bases, arm)
        if game.bases.runner_on(SECOND) is None:
            second_open = True
        else:
            second_open = False
        if game.bases.runner_on(THIRD) is None and game.bases.runner_on(SECOND):
            r = self.rng.random()
            if r < tag_from_second:
                second_open = True
                events.append(
                    RunnerAdvancedEvent(
                        game.bases.runner_on(SECOND),
                        pitcher=intent.pitcher,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="Tag up",
                        rbi_batter=game.current_batter,
                    )
                )

        if second_open and game.bases.runner_on(FIRST):
            r = self.rng.random()
            if r < tag_from_first:
                events.append(
                    RunnerAdvancedEvent(
                        game.bases.runner_on(FIRST),
                        pitcher=intent.pitcher,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="Tag up",
                        rbi_batter=game.current_batter,
                    )
                )

        events.append(FlyOutEvent(batter=intent.batter))
        events.append(PutOutEvent(self._select_outfielder(game)))
        events.append(OutRecordedEvent(reason="fly_out", pitcher=intent.pitcher))
        events.append(PlateAppearanceEndEvent(reason="fly_out", batter=intent.batter))

        return events

    def adjust_tagup_probs(self, bases: Bases, arm: int):
        tag_from_second = self.PROB_TAGUP_FROM_SECOND_FLYOUT
        tag_from_first = self.PROB_TAGUP_FROM_FIRST_FLYOUT
        if bases.runner_on(THIRD):
            tag_from_second = 0
        elif bases.runner_on(SECOND):
            # adjust based on random outfielder arm and scond base runner speed and baserunning skill
            speed = bases.runner_on(SECOND).skills["speed"]
            br_skill = bases.runner_on(SECOND).skills["base_running"]
            tag_from_second = tag_from_second * (speed + br_skill) / (2 * arm)

        if bases.runner_on(FIRST) and bases.one_man_on:
            speed = bases.runner_on(FIRST).skills["speed"]
            br_skill = bases.runner_on(FIRST).skills["base_running"]
            tag_from_first = tag_from_first * (speed + br_skill) / (2 * arm)

        return tag_from_second, tag_from_first

    def _resolve_ground_out(self, intent, game) -> list[GameEvent]:
        """Resolve a ground out"""
        events: list[GameEvent] = []

        # Determine which infielder fields the ball
        fielder = self._select_infielder(game)
        fielding_skill = fielder.skills["infield"]

        # Check if fielder makes an error
        error_prob = self._calculate_error_probability(fielding_skill)

        if self.rng.random() < error_prob:
            reason = "fielding_error"
            events.append(FieldingErrorEvent(fielder=fielder, batter=intent.batter))
            events.extend(self._handle_fielding_error_advancement(intent, game))
        else:
            # Successful out
            reason = "ground_out"
            events.append(GroundOutEvent(batter=intent.batter))
            events.append(
                PutOutEvent(
                    fielder=game.pitch_team.current_first_baseman, assist=fielder
                )
            )
            events.append(OutRecordedEvent(reason="ground_out", pitcher=intent.pitcher))
            events.extend(
                self._advance_all_runners(
                    game,
                    (THIRD, SECOND, FIRST),
                    advancement=1,
                    reason="ground_out",
                )
            )
        events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

        return events

    def _handle_fielding_error_advancement(self, intent, game) -> list[GameEvent]:
        # Advance all runners one base
        events: list[GameEvent] = []

        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="fielding_error",
                rbi_batter=intent.batter,
            )
        )

        # Batter to first
        events.append(
            self._advance_batter_to_base(
                intent.batter, intent.pitcher, FIRST, "fielding_error"
            )
        )

        return events

    def _resolve_home_run(self, intent, game) -> list[GameEvent]:
        """
        Resolve a home run.

        Score all the runners on base.
        Score the batter.
        """
        events: list[GameEvent] = []

        events.append(HomeRunEvent(batter=intent.batter, pitcher=intent.pitcher))

        # Score all runners
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=HOME,  # Will be capped at HOME
                reason="home_run",
                rbi_batter=intent.batter,
            )
        )

        # Batter scores
        events.append(
            RunnerAdvancedEvent(
                runner=intent.batter,
                from_base=None,
                to_base=HOME,
                reason="home_run",
                rbi_batter=intent.batter,
                pitcher=intent.pitcher,
            )
        )

        events.append(PlateAppearanceEndEvent(reason="home_run", batter=intent.batter))

        return events

    def _resolve_foul(self, intent, game) -> list[GameEvent]:
        """
        Resolve a foul ball.

        Must:
        - use rng
        - not mutate game
        - return concrete events
        """
        events: list[GameEvent] = []

        if game.count.strikes + 1 >= 3:
            r = self.rng.random()
            foul_tip_caught_prob = (
                self.FOUL_TIP_CAUGHT_PROB
                * game.pitch_team.current_catcher.skills["catching"]
                / 50
            )
            if r < foul_tip_caught_prob:
                self.logger.debug("foul tip strike out ending pa")
                events.extend(
                    [
                        FoulTipCaughtThirdStrikeEvent(),
                        StrikeOutEvent(batter=intent.batter, pitcher=intent.pitcher),
                        PutOutEvent(game.pitch_team.current_catcher),
                        OutRecordedEvent(reason="strikeout", pitcher=intent.pitcher),
                        PlateAppearanceEndEvent(
                            reason="strikeout", batter=intent.batter
                        ),
                    ]
                )
            elif r < self.FOULED_OFF_THIRD_STRIKE_PROB:
                events.append(FouledOffThirdStrikeEvent())
            else:
                events.extend(self._resolve_fly_out_foul(intent, game))

        else:  # less than 2 strikes
            r = self.rng.random()
            if r < self.FOUL_FLY_OUT_BEFORE_TWO_STRIKES_PROB:
                events.extend(self._resolve_fly_out_foul(intent, game))
            else:
                events.append(FoulStrikeEvent(swinging=True))

        return events

    def _resolve_fly_out_foul(self, intent, game) -> list[GameEvent]:
        """Simply resolves a fly out foul, can happen with 2 strikes or less."""

        return [
            FoulFlyOutEvent(batter=intent.batter),
            PutOutEvent(self._select_foul_out_catcher(game)),
            OutRecordedEvent(reason="foul_fly_out", pitcher=intent.pitcher),
            PlateAppearanceEndEvent(reason="out", batter=intent.batter),
        ]

    def _resolve_walk(
        self,
        intent,
        game,
        hbp=False,
        intentional=False,
        catcher_interference=False,
        skip_force_advance=False,
    ):
        """
        Resolves a walk. Will deal with hit by pitch, and intentional walks as well.

        Also handles the catcher interference case.

        It will force forward runners as necessary to make room for the batter on first.
        """
        self.logger.trace("Entering _resolve_walk")
        self.logger.debug(game.bases)

        events = []

        if hbp:
            reason = "intentional_hit_by_pitch" if intentional else "hit_by_pitch"
            events.append(HitByPitchEvent(batter=intent.batter, pitcher=intent.pitcher))
        else:
            if intentional:
                reason = "intentional_walk"
                events.append(IBBEvent(batter=intent.batter, pitcher=intent.pitcher))
            elif catcher_interference:
                reason = "catcher_interference"
                events.append(
                    CatcherInterferenceEvent(
                        batter=intent.batter,
                        pitcher=intent.pitcher,
                        catcher=game.pitch_team.current_catcher,
                    )
                )
            else:
                reason = "walk"
                events.append(WalkEvent(pitcher=intent.pitcher, batter=intent.batter))

        # Force existing runners
        if not skip_force_advance:
            occupied = game.bases.occupied_map()

            forced = force_advance_chain(
                occupied_bases=occupied,
                start_base=1,
                rbi_batter=intent.batter,
            )
            for f in forced:
                events.append(
                    RunnerAdvancedEvent(
                        runner=f.runner,
                        from_base=f.from_base,
                        to_base=f.to_base,
                        reason=f.reason,
                        rbi_batter=f.rbi_batter,
                        pitcher=intent.pitcher,
                    )
                )

        # Award batter first base
        events.append(
            self._advance_batter_to_base(intent.batter, intent.pitcher, FIRST, reason)
        )

        self.logger.trace("Ending PA in _resolve_walk")
        events.append(PlateAppearanceEndEvent(reason=reason, batter=intent.batter))

        return events

    def _resolve_single(self, intent, game):
        """
        Resolve a single with varied base advancement possibilities:
        - Runner on 2nd: usually scores, sometimes holds at 3rd
        - Runner on 1st: usually to 3rd, sometimes to 2nd, rarely scores
        - Batter always to 1st
        """
        events: list[GameEvent] = []

        events.append(SingleEvent(batter=intent.batter, pitcher=intent.pitcher))

        # Select outfielder who fields the ball
        fielder = self._select_outfielder(game)
        arm_strength = fielder.skills["arm"]

        # Handle runner on third (always scores on single)
        if game.bases.runner_on(THIRD):
            events.append(
                RunnerAdvancedEvent(
                    runner=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    to_base=HOME,
                    reason="single",
                    rbi_batter=intent.batter,
                    pitcher=intent.pitcher,
                )
            )

        held_at_third = False
        # Handle runner on second
        if game.bases.runner_on(SECOND):
            runner = game.bases.runner_on(SECOND)
            speed = runner.skills["speed"]
            baserunning = runner.skills["base_running"]

            # Base probability of scoring from second on a single: 60%
            base_score_prob = self.SCORE_FROM_SECOND_ON_SINGLE
            arm_factor = 50 / arm_strength  # Strong arm reduces scoring
            runner_factor = (speed + baserunning) / 100

            score_prob = base_score_prob * runner_factor * arm_factor

            if self.rng.random() < score_prob:
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=SECOND,
                        to_base=HOME,
                        reason="single",
                        rbi_batter=intent.batter,
                        pitcher=intent.pitcher,
                    )
                )
            else:
                held_at_third = True
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="single",
                        pitcher=intent.pitcher,
                    )
                )

        # Handle runner on first
        if game.bases.runner_on(FIRST):
            runner = game.bases.runner_on(FIRST)
            speed = runner.skills["speed"]
            baserunning = runner.skills["base_running"]

            # Base probability of first to third on a single: 35%
            base_f2t_prob = self.FIRST_TO_THIRD_ON_SINGLE
            base_fth_prob = self.FIRST_TO_HOME_ON_SINGLE
            arm_factor = 50 / arm_strength  # Strong arm reduces advancement
            runner_factor = (speed + baserunning) / 100

            first_to_third_prob = base_f2t_prob * runner_factor * arm_factor

            if self.rng.random() < base_fth_prob and not held_at_third:
                # First to home
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=HOME,
                        reason="single",
                        rbi_batter=intent.batter,
                        pitcher=intent.pitcher,
                    )
                )
            elif self.rng.random() < first_to_third_prob and not held_at_third:
                # First to third
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=THIRD,
                        reason="single",
                        pitcher=intent.pitcher,
                    )
                )
            else:
                # First to second
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="single",
                        pitcher=intent.pitcher,
                    )
                )

        # Batter to first
        events.append(
            self._advance_batter_to_base(intent.batter, intent.pitcher, FIRST, "single")
        )

        events.append(PlateAppearanceEndEvent(reason="single", batter=intent.batter))

        return events

    def _resolve_double(self, intent, game):
        """
        Resolve a double:
        - All runners advance two bases by default
        - Batter to second
        - Plate appearance ends
        Also, sometimes they can be thrown out.
        """
        events: list[GameEvent] = []

        events.append(DoubleEvent(batter=intent.batter, pitcher=intent.pitcher))

        # Select which outfielder fields the ball
        fielder = self._select_outfielder(game)
        arm_strength = fielder.skills["arm"]

        if game.bases.runner_on(FIRST):
            speed = game.bases.runner_on(FIRST).skills["speed"]
            skill = game.bases.runner_on(FIRST).skills["base_running"]
            # Advance runners on second and third two bases
            events.extend(
                self._advance_all_runners(
                    game,
                    (THIRD, SECOND),
                    advancement=2,
                    reason="double",
                    rbi_batter=intent.batter,
                )
            )
            # Calculate scoring probability based on arm strength
            base_score_prob = self.SCORE_FROM_FIRST_ON_DOUBLE
            arm_factor = 50 / arm_strength  # Strong arm reduces scoring
            runner_factor = (speed + skill) / 100
            score_prob = base_score_prob * runner_factor * arm_factor

            if self.rng.random() < score_prob:
                events.append(
                    RunnerAdvancedEvent(
                        runner=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        to_base=HOME,
                        reason="double",
                        rbi_batter=intent.batter,
                        pitcher=intent.pitcher,
                    )
                )
            else:
                # Check if runner is thrown out trying to score
                throw_out_prob = self._calculate_throw_out_probability(
                    arm_strength, speed, skill
                )
                if self.rng.random() < throw_out_prob:
                    events.extend(
                        [
                            PutOutEvent(
                                fielder=game.pitch_team.current_catcher, assist=fielder
                            ),
                            OutRecordedEvent(
                                reason="thrown_out_at_home", pitcher=intent.pitcher
                            ),
                            RunnerRemovedEvent(
                                runner=game.bases.runner_on(FIRST),
                                from_base=FIRST,
                                reason="thrown_out_at_home",
                            ),
                        ]
                    )
                else:
                    events.append(
                        RunnerAdvancedEvent(
                            runner=game.bases.runner_on(FIRST),
                            from_base=FIRST,
                            to_base=THIRD,
                            reason="double",
                            pitcher=intent.pitcher,
                        )
                    )

        else:
            # Advance all runners two bases
            events.extend(
                self._advance_all_runners(
                    game,
                    (THIRD, SECOND, FIRST),
                    advancement=2,
                    reason="double",
                    rbi_batter=intent.batter,
                )
            )

        # Batter to second
        events.append(
            self._advance_batter_to_base(
                intent.batter, intent.pitcher, SECOND, "double"
            )
        )

        events.append(PlateAppearanceEndEvent(reason="double", batter=intent.batter))

        return events

    def _resolve_triple(self, intent, game):
        """
        Resolve a triple:
        - All runners score by default
        - Batter to third
        - Plate appearance ends
        """
        events: list[GameEvent] = []

        events.append(TripleEvent(batter=intent.batter, pitcher=intent.pitcher))

        # All runners score (advancement to HOME)
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=HOME,  # Will be capped at HOME
                reason="triple",
                rbi_batter=intent.batter,
            )
        )

        # Batter to third
        events.append(
            self._advance_batter_to_base(intent.batter, intent.pitcher, THIRD, "triple")
        )

        events.append(PlateAppearanceEndEvent(reason="triple", batter=intent.batter))

        return events

    def _resolve_double_play(self, intent, game):
        """
        Resolve a double play:
        - Default runner on first is out via force
        - And batter/runner is out

        - Other runners could advance and potentially score

        - If no runner on first, another runner must be put out
        - plus the batter/runner or another runner

        - There must be two outs.

        - Plate appearance ends
        """
        # Validation
        self._validate_game_state(game, max_outs=2, require_runners=True)

        events: list[GameEvent] = []

        events.append(DoublePlayEvent(batter=intent.batter, pitcher=intent.pitcher))
        if game.bases.runner_on(FIRST):
            # pick double play type
            events.extend(self._choose_double_play(game))
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(FIRST),
                    from_base=FIRST,
                    reason="double_play",
                )
            )
            events.extend(
                self._advance_all_runners(
                    game,
                    (THIRD, SECOND),
                    advancement=1,
                    reason="double_play",
                )
            )

        # No runner was on first, but we still need a double play
        # try third next.
        elif game.bases.runner_on(THIRD):
            events.extend(self._3to1_double_play(game))
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    reason="double_play",
                )
            )
            if game.bases.runner_on(SECOND) and game.bases.runner_on(FIRST):
                runner = game.bases.runner_on(SECOND)
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )
                runner = game.bases.runner_on(FIRST)
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )
            elif game.bases.runner_on(SECOND):
                r = self.rng.random()
                if r < 0.67:
                    runner = game.bases.runner_on(SECOND)
                    events.append(
                        RunnerAdvancedEvent(
                            runner=runner,
                            from_base=SECOND,
                            to_base=THIRD,
                            reason="fielders_choice",
                            pitcher=intent.pitcher,
                        )
                    )
            elif game.bases.runner_on(FIRST):
                runner = game.bases.runner_on(FIRST)
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )
        else:
            # must be a runner on second.
            events.extend(self._2to1_double_play(game))
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="double_play",
                )
            )
            if game.bases.runner_on(FIRST):
                runner = game.bases.runner_on(FIRST)
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=FIRST,
                        to_base=SECOND,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )

        events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))
        events.append(
            PlateAppearanceEndEvent(reason="double_play", batter=intent.batter)
        )

        return events

    def _choose_double_play(self, game) -> list[PutOutEvent]:
        """
        Pick a type of double play to perform, and return the proper PutOutEvent
        """
        events: list[GameEvent] = []
        dp_type = self.double_play_choice.choose()
        if dp_type == "6-4-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_second_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )
        elif dp_type == "4-6-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                    game.pitch_team.current_second_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        elif dp_type == "5-4-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_second_baseman,
                    game.pitch_team.current_third_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )
        elif dp_type == "6-3":
            events.append(PutOutEvent(game.pitch_team.current_shortstop))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        elif dp_type == "4-3":
            events.append(PutOutEvent(game.pitch_team.current_second_baseman))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )
        elif dp_type == "3-6-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                    game.pitch_team.current_first_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        elif dp_type == "1-6-3":
            events.append(
                PutOutEvent(game.pitch_team.current_shortstop, game.current_pitcher)
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        elif dp_type == "3-6":
            events.append(PutOutEvent(game.pitch_team.current_first_baseman))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                    game.pitch_team.current_first_baseman,
                )
            )
        elif dp_type == "3-6-1":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                    game.pitch_team.current_first_baseman,
                )
            )
            events.append(
                PutOutEvent(game.current_pitcher, game.pitch_team.current_shortstop)
            )
        else:  # back to 6-4-3
            events.append(
                PutOutEvent(
                    game.pitch_team.current_second_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )
        return events

    def _3to1_double_play(self, game) -> list[PutOutEvent]:
        """
        Pick a type of double play to perform, and return the proper PutOutEvent.
        In this case we are putting out the batter and a runner on third.
        """
        events: list[GameEvent] = []
        dp_type = self._3to1_dp_choice.choose()
        if dp_type == "5-2-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher,
                    game.pitch_team.current_third_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_catcher,
                )
            )
        elif dp_type == "6-2-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher,
                    game.pitch_team.current_shortstop,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_catcher,
                )
            )
        elif dp_type == "4-2-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher,
                    game.pitch_team.current_second_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_catcher,
                )
            )
        elif dp_type == "1-2-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher,
                    game.current_pitcher,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_catcher,
                )
            )
        elif dp_type == "3-2-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher,
                    game.pitch_team.current_first_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_catcher,
                )
            )
        elif dp_type == "5-5":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_third_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_third_baseman,
                )
            )
        elif dp_type == "6-5":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_third_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        else:  # "4-5"
            events.append(
                PutOutEvent(
                    game.pitch_team.current_second_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_third_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )

        return events

    def _2to1_double_play(self, game) -> list[PutOutEvent]:
        """
        Pick a type of double play to perform, and return the proper PutOutEvent.
        In this case we are putting out the batter and a runner on second.
        """
        events: list[GameEvent] = []
        dp_type = self._2to1_dp_choice.choose()

        if dp_type == "6-3":
            events.append(PutOutEvent(game.pitch_team.current_shortstop))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
        elif dp_type == "6-5-3":
            events.append(
                PutOutEvent(
                    game.pitch_team.current_third_baseman,
                    game.pitch_team.current_shortstop,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_third_baseman,
                )
            )
        elif dp_type == "5-3":
            events.append(PutOutEvent(game.pitch_team.current_third_baseman))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_third_baseman,
                )
            )
        elif dp_type == "4-6":
            events.append(PutOutEvent(game.pitch_team.current_second_baseman))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_shortstop,
                    game.pitch_team.current_second_baseman,
                )
            )
        return events

    def _resolve_fielders_choice(self, intent, game):
        """
        Fielder's choice can result in no outs.

        The official scorers must deem that had the fielder chosen to throw to
        1B, that it would have been a routine play.

        If they try to get the lead runner instead and fail, then it would be
        a fielder's choice.

        A run scores on a fielder's choice when the defense prioritizes getting
        another runner, and that play allows the run to cross the plate before
        the defense gets an out on the batter or another forced runner.

        The default is one out, but there doesn't need to be an out necessarily

        algorithm:
        - pick one runner to put out, move all other runners forward one base.
        - If there is a runner on third, pick that one
        - Else pick the runner on first
        - Else the runner on second
        - Place the batter on first
        """
        # Validation
        self._validate_game_state(game, max_outs=2, require_runners=True)

        events: list[GameEvent] = []
        events.append(FieldersChoiceEvent(batter=intent.batter, pitcher=intent.pitcher))

        if game.bases.runner_on(THIRD):
            # throw out at plate
            events.append(
                PutOutEvent(
                    game.pitch_team.current_catcher, self._select_infielder(game)
                )
            )
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    reason="fielders_choice",
                )
            )
            # Advance other runners
            events.extend(
                self._advance_all_runners(
                    game,
                    (SECOND, FIRST),
                    advancement=1,
                    reason="fielders_choice",
                )
            )

        elif game.bases.runner_on(FIRST):
            # force out at second
            if self.rng.random() < 0.5:
                if self.rng.random() < 0.7:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_shortstop,
                            game.pitch_team.current_second_baseman,
                        )
                    )
                else:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_shortstop,
                            game.pitch_team.current_third_baseman,
                        )
                    )
            else:
                if self.rng.random() < 0.7:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_second_baseman,
                            game.pitch_team.current_shortstop,
                        )
                    )
                else:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_second_baseman,
                            game.pitch_team.current_third_baseman,
                        )
                    )
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(FIRST),
                    from_base=FIRST,
                    reason="fielders_choice",
                )
            )
            # Advance runner on second if present
            runner = game.bases.runner_on(SECOND)
            if runner:
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="fielders_choice",
                        pitcher=intent.pitcher,
                    )
                )

        else:
            # runner on second, just have the shortstop tag him out
            events.append(PutOutEvent(game.pitch_team.current_shortstop))
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="fielders_choice",
                )
            )

        # Batter to first
        events.append(
            self._advance_batter_to_base(
                intent.batter, intent.pitcher, FIRST, "fielders_choice"
            )
        )
        events.append(
            OutRecordedEvent(reason="fielders_choice", pitcher=intent.pitcher)
        )
        events.append(
            PlateAppearanceEndEvent(reason="fielders_choice", batter=intent.batter)
        )

        return events

    def _resolve_sac_bunt(self, intent, game):
        """
        A sac bunt must be a bunt. There can't be 2 outs.

        - move a runner from 1st to 2nd if no other runners
        - move a runner from 2nd to third if no other runners
        - score a runner from 3rd if no other runners
        - all runners should advance if multiple.
        - put out the batter
        """
        # Validation
        self._validate_game_state(game, max_outs=2, require_runners=True)

        events: list[GameEvent] = []

        events.append(SacBuntEvent(batter=intent.batter))
        events.append(
            PutOutEvent(
                game.pitch_team.current_first_baseman, self._select_infielder_bunt(game)
            )
        )
        events.append(OutRecordedEvent(reason="sac_bunt", pitcher=intent.pitcher))

        # Advance all runners one base
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="sac_bunt",
                rbi_batter=intent.batter,
            )
        )

        events.append(PlateAppearanceEndEvent(reason="sac_bunt", batter=intent.batter))

        return events

    def _resolve_sac_fly(self, intent, game):
        """
        A sac fly must result in a score. There can't be 2 outs.

        - score the runner on third
        - put out the batter
        """
        # Validation
        self._validate_game_state(game, max_outs=2, require_runner_on=THIRD)

        events: list[GameEvent] = []

        events.append(SacFlyEvent(batter=intent.batter))
        events.append(PutOutEvent(self._select_outfielder(game)))
        events.append(OutRecordedEvent(reason="sac_fly", pitcher=intent.pitcher))

        runner = game.bases.runner_on(THIRD)
        events.append(
            RunnerAdvancedEvent(
                runner=runner,
                from_base=THIRD,
                to_base=HOME,
                reason="sac_fly",
                rbi_batter=intent.batter,
                pitcher=intent.pitcher,
            )
        )
        # Advance the runners from first and second also
        # Should be a variable chance to change this.
        events.extend(
            self._advance_all_runners(
                game,
                (SECOND, FIRST),
                advancement=1,
                reason="ground_out",
            )
        )

        events.append(PlateAppearanceEndEvent(reason="sac_fly", batter=intent.batter))

        return events

    def _resolve_triple_play(self, intent, game):
        """
        Resolve a triple play:
        - If bases are loaded, we pick 2 runners randomly to put out

        - Otherwise, both runners are put out from whatever base they are on

        - There must be three outs.

        - Plate appearance ends
        """
        # Validation
        if game.inning.outs > 0:
            raise RuntimeError(
                "Triple play cannot occur with outs already in the inning."
            )
        if len(game.bases.occupied_map()) < 2:
            raise RuntimeError(
                "Triple play cannot occur without at least 2 runners on base."
            )

        events: list[GameEvent] = []

        events.append(TriplePlayEvent(batter=intent.batter))

        if game.bases.is_loaded:
            r = self.rng.random()
            if r < self.TRIPLE_PLAY_FIRST_SECOND_THRESHOLD:
                # hard coded around the horn
                events.append(PutOutEvent(game.pitch_team.current_third_baseman))
                events.append(
                    PutOutEvent(
                        game.pitch_team.current_second_baseman,
                        game.pitch_team.current_third_baseman,
                    )
                )
                events.append(
                    PutOutEvent(
                        game.pitch_team.current_first_baseman,
                        game.pitch_team.current_second_baseman,
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
            elif r < self.TRIPLE_PLAY_FIRST_THIRD_THRESHOLD:
                # hard coded line out to third baseman, tag third, throw behind runner leaving first
                events.append(PutOutEvent(game.pitch_team.current_third_baseman))
                events.append(PutOutEvent(game.pitch_team.current_third_baseman))
                events.append(
                    PutOutEvent(
                        game.pitch_team.current_first_baseman,
                        game.pitch_team.current_third_baseman,
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )
            else:
                # hard coded around the horn
                events.append(PutOutEvent(game.pitch_team.current_third_baseman))
                events.append(
                    PutOutEvent(
                        game.pitch_team.current_second_baseman,
                        game.pitch_team.current_third_baseman,
                    )
                )
                events.append(
                    PutOutEvent(
                        game.pitch_team.current_first_baseman,
                        game.pitch_team.current_second_baseman,
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
        else:  # bases not loaded, must be two runners on, and both are out
            # hard coded around the horn
            events.append(PutOutEvent(game.pitch_team.current_third_baseman))
            events.append(
                PutOutEvent(
                    game.pitch_team.current_second_baseman,
                    game.pitch_team.current_third_baseman,
                )
            )
            events.append(
                PutOutEvent(
                    game.pitch_team.current_first_baseman,
                    game.pitch_team.current_second_baseman,
                )
            )
            if game.bases.runner_on(FIRST):
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
            if game.bases.runner_on(SECOND):
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
            if game.bases.runner_on(THIRD):
                events.append(
                    RunnerRemovedEvent(
                        runner=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )

        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))
        events.append(
            PlateAppearanceEndEvent(reason="triple_play", batter=intent.batter)
        )

        return events

    def _select_infielder_bunt(self, game):
        """Randomly select which infielder fields a bunted ball"""
        position = self.infielder_bunt_choice.choose()

        position_map = {
            "shortstop": game.pitch_team.current_shortstop,
            "second_baseman": game.pitch_team.current_second_baseman,
            "third_baseman": game.pitch_team.current_third_baseman,
            "first_baseman": game.pitch_team.current_first_baseman,
            "pitcher": game.current_pitcher,
            "catcher": game.pitch_team.current_catcher,
        }

        return position_map[position]

    def _select_infielder(self, game):
        """Randomly select which infielder fields a ground ball"""
        position = self.infielder_choice.choose()

        position_map = {
            "shortstop": game.pitch_team.current_shortstop,
            "second_baseman": game.pitch_team.current_second_baseman,
            "third_baseman": game.pitch_team.current_third_baseman,
            "first_baseman": game.pitch_team.current_first_baseman,
            "pitcher": game.current_pitcher,
        }

        return position_map[position]

    def _select_outfielder(self, game):
        """Randomly select which outfielder fields a fly ball"""
        position = self.outfielder_choice.choose()

        position_map = {
            "center_fielder": game.pitch_team.current_center_fielder,
            "right_fielder": game.pitch_team.current_right_fielder,
            "left_fielder": game.pitch_team.current_left_fielder,
        }

        return position_map[position]

    def _select_foul_out_catcher(self, game):
        """Randomly select which outfielder fields a fly ball"""
        position = self.foul_fly_choice.choose()

        position_map = {
            "center_fielder": game.pitch_team.current_center_fielder,
            "right_fielder": game.pitch_team.current_right_fielder,
            "left_fielder": game.pitch_team.current_left_fielder,
            "shortstop": game.pitch_team.current_shortstop,
            "second_baseman": game.pitch_team.current_second_baseman,
            "third_baseman": game.pitch_team.current_third_baseman,
            "first_baseman": game.pitch_team.current_first_baseman,
            "pitcher": game.current_pitcher,
            "catcher": game.pitch_team.current_catcher,
        }

        return position_map[position]


class EnhancedResolver(Resolver):
    """
    Extended Resolver with pre-pitch and concurrent event support.
    """

    def __init__(self, rng):
        super().__init__(rng)

        # ============================================================
        # Initialize steal outcome choosers
        # ============================================================
        self.double_steal_choice = WeightedChoice(
            {
                "both_safe": 900,
                "lead_out_trail_safe": 2500,
                "lead_safe_trail_out": 800,
                "both_out": 100,
            },
            rng=rng,
        )

        self.first_and_third_choice = WeightedChoice(
            {
                "both_safe": 600,
                "first_advances_only": 1500,
                "first_out_third_scores": 1000,
                "third_out_first_advances": 2800,
                "both_out": 100,
            },
            rng=rng,
        )

    def resolve(self, intent: GameIntent, game) -> List[GameEvent]:
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
            return self._resolve_pickoff(intent, game)

        if isinstance(intent, PitchIntent):
            events = []
            situation = intent.pre_pitch_situation

            # Special case: intentional walk skips pitch
            if situation.intentional_walk:
                events.extend(self._resolve_walk(intent, game, intentional=True))
                return events

            # ============================================================
            # Phase 1: The pitch itself
            # ============================================================
            pitch_events = self._resolve_pitch(intent, game)

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
            ):
                # Steals can happen on balls, strikes,
                # but not balks, walks, errors, wild pitches, passed balls, fouls or ball_in_play
                concurrent_events = self._resolve_concurrent_events(intent, game)

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
            else:
                # Ball in play - no concurrent steal events
                events.extend(pitch_events)

            return events

        raise RuntimeError(f"Unhandled intent type: {type(intent).__name__}")

    def _modify_first_and_third_probs(self, game):
        """
        Apply modifiers for first-and-third double steal.

        BEFORE: Direct manipulation of self.first_and_third_probs dict
        AFTER: Use WeightedChoice methods
        """
        speed1 = game.bases.runner_on(FIRST).skills["speed"]
        br1 = game.bases.runner_on(FIRST).skills["base_running"]
        speed3 = game.bases.runner_on(THIRD).skills["speed"]
        br3 = game.bases.runner_on(THIRD).skills["base_running"]
        arm = game.pitch_team.current_catcher.skills["arm"]
        arm2 = game.pitch_team.current_second_baseman.skills["arm"]

        # Calculate skill factor
        runner_factor = (speed1 + br1 + speed3 + br3) / 200
        defense_factor = 50 / arm
        defense_factor2 = 50 / arm2

        # Apply multipliers
        self.first_and_third_choice.multiply(
            "both_safe", runner_factor * defense_factor
        )
        self.first_and_third_choice.multiply(
            "first_advances_only", runner_factor * defense_factor
        )
        self.first_and_third_choice.multiply(
            "first_out_third_scores", runner_factor * defense_factor * defense_factor2
        )
        self.first_and_third_choice.multiply(
            "third_out_first_advances", runner_factor * defense_factor * defense_factor2
        )

        # Inverse multiplier for both_out
        both_out_factor = (
            (200 / (speed1 + br1 + speed3 + br3)) * (arm / 50) * (arm2 / 50)
        )
        self.first_and_third_choice.multiply("both_out", both_out_factor)

    def _modify_double_steal_probs(self, game):
        """
        Apply modifiers for standard double steal.

        BEFORE: Direct manipulation of self.double_steal_probs dict
        AFTER: Use WeightedChoice methods
        """
        if game.bases.runner_on(FIRST):
            runner1 = game.bases.runner_on(FIRST)
            runner2 = game.bases.runner_on(SECOND)
            arm2 = game.pitch_team.current_third_baseman.skills["arm"]
        else:
            runner1 = game.bases.runner_on(SECOND)
            runner2 = game.bases.runner_on(THIRD)
            arm2 = None

        speed1 = runner1.skills["speed"]
        br1 = runner1.skills["base_running"]
        speed2 = runner2.skills["speed"]
        br2 = runner2.skills["base_running"]
        arm = game.pitch_team.current_catcher.skills["arm"]
        catcher = game.pitch_team.current_catcher.skills["catching"]

        runner_factor = (speed1 + br1 + speed2 + br2) / 200
        defense_factor = 50 / arm

        self.double_steal_choice.multiply("both_safe", runner_factor * defense_factor)

        if arm2:
            both_out_factor = (
                (200 / (speed1 + br1 + speed2 + br2)) * (arm / 50) * (arm2 / 50)
            )
        else:
            both_out_factor = (
                (200 / (speed1 + br1 + speed2 + br2)) * (arm / 50) * (catcher / 50)
            )

        self.double_steal_choice.multiply("both_out", both_out_factor)

    def _resolve_pickoff(self, intent: PickOffIntent, game) -> List[GameEvent]:
        """
        Resolve a pickoff attempt.

        Possible outcomes:
        1. Successful pickoff (runner out)
        2. Failed pickoff (runner safe, no advancement)
        3. Throwing error (runner advances)
        """
        events = []
        base = intent.target_base
        runner = game.bases.runner_on(base)

        if not runner:
            return events

        events.append(
            PickoffAttemptEvent(base=base, runner=runner, pitcher=intent.pitcher)
        )

        # Determine outcome
        r = self.rng.random()

        pickoff_success_prob, pickoff_error_prob = self.adjust_pickoff_success(
            base, intent.pitcher, game, runner.skills["base_running"], intent.steal_on
        )
        # base_running skill of runner
        if r < pickoff_success_prob:
            # Successful pickoff - runner out
            self.logger.debug(f"Successful pickoff at base {base}")
            events.append(
                PickoffSuccessEvent(base=base, runner=runner, pitcher=intent.pitcher)
            )
            if base == THIRD:
                fielder = game.pitch_team.current_third_baseman
            elif base == SECOND:
                if self.rng.random() < 0.55:
                    fielder = game.pitch_team.current_shortstop
                else:
                    fielder = game.pitch_team.current_second_baseman
            else:
                fielder = game.pitch_team.current_first_baseman
            events.append(PutOutEvent(fielder=fielder, assist=intent.pitcher))
            events.append(OutRecordedEvent(reason="pickoff", pitcher=intent.pitcher))
            events.append(
                RunnerRemovedEvent(runner=runner, from_base=base, reason="pickoff")
            )

        elif r < pickoff_success_prob + pickoff_error_prob:
            # Throwing error - runner advances
            self.logger.debug(f"Pickoff throwing error at base {base}")
            events.append(
                PickoffErrorEvent(base=base, runner=runner, pitcher=intent.pitcher)
            )
            # Advance all runners one base
            events.extend(
                self._advance_all_runners(
                    game,
                    (THIRD, SECOND, FIRST),
                    advancement=1,
                    reason="pickoff_error",
                )
            )

        else:
            # Runner safe, no advancement
            self.logger.debug(f"Failed pickoff attempt at base {base}")
            events.append(
                PickoffFailedEvent(base=base, runner=runner, pitcher=intent.pitcher)
            )

        return events

    def adjust_pickoff_success(
        self, base: int, pitcher: PlayerInGame, game, br_skill=50, steal_on=False
    ):
        success = self.PICKOFF_SUCCESS_PROB
        error = self.PICKOFF_ERROR_PROB
        self.logger.trace(
            f"pickoff success vars, base={base}, pitcher.throws={pitcher.throws}, baserunning={br_skill}"
        )
        if base is FIRST and pitcher.throws[0].lower() == "l":
            success *= 1.1
        if base is THIRD and pitcher.throws[0].lower() == "r":
            success *= 1.1
        success = success * 50 / max(30, br_skill)
        accuracy = pitcher.get_effective_stat(pitcher.skills["accuracy"])
        error *= 50 / max(30, accuracy)
        if base is FIRST:
            error *= 50 / max(
                1, game.pitch_team.current_first_baseman.skills["infield"]
            )
        if base is SECOND:
            r = self.rng.random()
            # 50/50 2nd baseman or short stop
            if r < 0.5:
                error *= 50 / max(
                    1, game.pitch_team.current_second_baseman.skills["infield"]
                )
            else:
                error *= 50 / max(
                    1, game.pitch_team.current_shortstop.skills["infield"]
                )
        if base is THIRD:
            error *= 50 / max(
                1, game.pitch_team.current_third_baseman.skills["infield"]
            )
        if steal_on:
            success *= self.STEAL_ON_PICKOFF_MODIFIER
        return success, error

    # ================================================================
    # CONCURRENT EVENT RESOLUTION (STEALS)
    # ================================================================

    def _resolve_concurrent_events(self, intent: PitchIntent, game) -> List[GameEvent]:
        """
        Resolve events that happen concurrently with the pitch.

        NOTE: Steals currently do NOT happen on walks, as runners are
        already being force-advanced. This is slightly broken, as a steal
        could happen by an unforced runner. We just don't currently allow it.

        NOTE: Steals should NOT happen if runners are already being advanced
        by a wild pitch or passed ball. We should adjust so that runner
        advancement isn't 100% but steal makes it even more likely

        NOTE: Steals won't happen on a ball_in_play, as they are handled
        in _resolve_ball_in_play

        """
        events = []

        if game.bases.is_empty:
            return events
        double_steal_bases = None
        from_base = None

        # Check for hit and run double steal scenarios
        if intent.pre_pitch_situation.hit_and_run:
            if game.bases.two_men_on:
                self.logger.debug("Hit and run double steal")
                double_steal_bases = GameStrategy.get_double_steal_candidates(game)
        else:
            double_steal_bases = intent.pre_pitch_situation.double_steal_attempt

        if double_steal_bases:
            return self._resolve_double_steal(double_steal_bases, intent, game)
        if intent.pre_pitch_situation.hit_and_run:
            self.logger.debug("Hit and run steal")
            from_base = game.bases.only_occupied_base()
        else:
            from_base = intent.pre_pitch_situation.steal_attempt
        if from_base:
            return self._resolve_steal_attempt(from_base, intent, game)

        return events

    def _resolve_steal_attempt(
        self, from_base: int, intent: PitchIntent, game
    ) -> List[GameEvent]:
        """
        Resolve a single steal attempt.

        Outcomes:
        - Successful steal
        - Caught stealing
        """
        events = []
        runner = game.bases.runner_on(from_base)
        to_base = from_base + 1

        if not runner:
            return events

        events.append(
            StealAttemptEvent(runner=runner, from_base=from_base, to_base=to_base)
        )

        arm = game.pitch_team.current_catcher.skills["arm"]

        if to_base == SECOND:
            success_prob = self.STEAL_SECOND_SUCCESS_PROB

        elif to_base == THIRD:
            success_prob = self.STEAL_THIRD_SUCCESS_PROB
        elif to_base == HOME:
            success_prob = self.STEAL_HOME_SUCCESS_PROB
            arm = 50  # We just set this to average as it's not relevant
        else:
            success_prob = 0.50

        success_prob = self.adjust_steal_prob(
            success_prob,
            game.bases.runner_on(from_base).skills["speed"],
            game.bases.runner_on(from_base).skills["base_running"],
            arm,
            game.pitch_team.current_catcher.skills["catching"],
        )

        if self.rng.random() < success_prob:
            # Successful steal
            self.logger.debug(f"Successful steal: {from_base} -> {to_base}")
            events.append(
                StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
            )
            events.append(
                RunnerAdvancedEvent(
                    runner=runner,
                    from_base=from_base,
                    to_base=to_base,
                    reason="stolen_base",
                    pitcher=intent.pitcher,
                )
            )
        else:
            # Caught stealing
            self.logger.debug(f"Caught stealing: {from_base} -> {to_base}")
            events.append(
                CaughtStealingEvent(runner=runner, from_base=from_base, to_base=to_base)
            )
            assist = game.pitch_team.current_catcher
            if to_base == SECOND:
                if self.rng.random() < 0.55:
                    fielder = game.pitch_team.current_shortstop
                else:
                    fielder = game.pitch_team.current_second_baseman
            elif to_base == THIRD:
                fielder = game.pitch_team.current_third_baseman
            else:
                fielder = game.pitch_team.current_catcher
                assist = game.current_pitcher
            events.append(PutOutEvent(fielder=fielder, assist=assist))
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )

        return events

    def adjust_steal_prob(
        self, prob, run_speed=50, base_running=50, catcher_arm=50, catching_skill=50
    ) -> float:
        return (
            (run_speed + base_running) / max(1, (catcher_arm + catching_skill)) * prob
        )

    def _resolve_double_steal(
        self, from_bases: List[int], intent: PitchIntent, game
    ) -> List[GameEvent]:
        """
        Resolve a double steal attempt.

        Args:
            from_bases: Bases runners are currently on (e.g., [1, 2])
        """
        events = []

        # CRITICAL: Sort in reverse order (lead runner first)
        # This ensures we advance 2nd→3rd BEFORE 1st→2nd
        sorted_bases = sorted(from_bases, reverse=True)

        # Build steal attempt info (in reverse order)
        steal_attempts = [
            (from_base, from_base + 1, game.bases.runner_on(from_base))
            for from_base in sorted_bases
        ]

        # Record all attempts (order doesn't matter for logging)
        for from_base, to_base, runner in steal_attempts:
            events.append(
                StealAttemptEvent(runner=runner, from_base=from_base, to_base=to_base)
            )

        events.append(DoubleStealAttemptEvent(bases=from_bases))

        # Check if this is 1st and 3rd scenario
        is_first_and_third = FIRST in from_bases and THIRD in from_bases

        if is_first_and_third:
            # Reset to base probabilities and apply modifiers
            self.first_and_third_choice.reset()
            self._modify_first_and_third_probs(game)
            result = self.first_and_third_choice.choose()
            # # 1st and 3rd special handling
            first_attempt = next(a for a in steal_attempts if a[0] == FIRST)
            third_attempt = next(a for a in steal_attempts if a[0] == THIRD)

            if result == "both_safe":
                # Both safe - ADVANCE IN REVERSE ORDER
                # Third → Home first, then First → Second
                from_base, to_base, runner = third_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )

                from_base, to_base, runner = first_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )
            elif result == "first_advances_only":
                # Only runner on 1st steals (runner on 3rd holds)
                from_base, to_base, runner = first_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )
            elif result == "first_out_third_scores":
                # Runner on 1st out, runner on 3rd scores
                from_base, to_base, runner = third_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )

                from_base, to_base, runner = first_attempt
                events.append(
                    CaughtStealingEvent(
                        runner=runner, from_base=from_base, to_base=to_base
                    )
                )
                if self.rng.random() < 0.55:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_shortstop,
                            game.pitch_team.current_catcher,
                        )
                    )
                else:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_second_baseman,
                            game.pitch_team.current_catcher,
                        )
                    )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner, from_base=from_base, reason="caught_stealing"
                    )
                )
            elif result == "third_out_first_advances":
                # Runner on 3rd caught, runner on 1st safe
                from_base, to_base, runner = third_attempt
                events.append(
                    CaughtStealingEvent(
                        runner=runner, from_base=from_base, to_base=to_base
                    )
                )
                events.append(
                    PutOutEvent(game.pitch_team.current_catcher, game.current_pitcher)
                )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner, from_base=from_base, reason="caught_stealing"
                    )
                )

                from_base, to_base, runner = first_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )
            elif result == "both_out":
                # Both out
                if self.rng.random() < 0.55:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_shortstop,
                            game.pitch_team.current_catcher,
                        )
                    )
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_catcher,
                            game.pitch_team.current_shortstop,
                        )
                    )
                else:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_second_baseman,
                            game.pitch_team.current_catcher,
                        )
                    )
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_catcher,
                            game.pitch_team.current_second_baseman,
                        )
                    )
                for from_base, to_base, runner in steal_attempts:
                    events.append(
                        CaughtStealingEvent(
                            runner=runner, from_base=from_base, to_base=to_base
                        )
                    )
                    events.append(
                        OutRecordedEvent(
                            reason="caught_stealing", pitcher=intent.pitcher
                        )
                    )
                    events.append(
                        RunnerRemovedEvent(
                            runner=runner,
                            from_base=from_base,
                            reason="caught_stealing",
                        )
                    )
            else:
                raise RuntimeError(f"Unknown result={result} first_and_third_probs")

        else:
            # Reset to base probabilities and apply modifiers
            self.double_steal_choice.reset()
            self._modify_double_steal_probs(game)
            result = self.double_steal_choice.choose()

            # Standard double steal (1st/2nd or 2nd/3rd)
            # steal_attempts is already sorted in reverse order (lead runner first)
            if result == "both_safe":
                # Both safe - process in order (lead runner first)
                for from_base, to_base, runner in steal_attempts:
                    events.append(
                        StolenBaseEvent(
                            runner=runner, from_base=from_base, to_base=to_base
                        )
                    )
                    events.append(
                        RunnerAdvancedEvent(
                            runner=runner,
                            from_base=from_base,
                            to_base=to_base,
                            reason="stolen_base",
                            pitcher=intent.pitcher,
                        )
                    )
            elif result == "lead_out_trail_safe":
                # Validate: ensure we have exactly 2 runners
                if len(steal_attempts) != 2:
                    raise RuntimeError(
                        f"lead_out_trail_safe requires exactly 2 runners, got {len(steal_attempts)}"
                    )

                # Lead runner out, trail runner safe
                lead_attempt = steal_attempts[0]  # First in list (highest base)
                trail_attempt = steal_attempts[1]  # Second in list (lowest base)

                from_base, to_base, runner = lead_attempt
                events.append(
                    CaughtStealingEvent(
                        runner=runner, from_base=from_base, to_base=to_base
                    )
                )
                if to_base == HOME:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_catcher, game.current_pitcher
                        )
                    )
                elif to_base == THIRD:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_third_baseman,
                            game.pitch_team.current_catcher,
                        )
                    )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner, from_base=from_base, reason="caught_stealing"
                    )
                )

                from_base, to_base, runner = trail_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )
            elif result == "lead_safe_trail_out":
                # Validate: ensure we have exactly 2 runners
                if len(steal_attempts) != 2:
                    raise RuntimeError(
                        f"lead_safe_trail_out requires exactly 2 runners, got {len(steal_attempts)}"
                    )

                # Trail runner out, lead runner safe
                lead_attempt = steal_attempts[0]
                trail_attempt = steal_attempts[1]

                # Lead runner advances first (to clear the base)
                from_base, to_base, runner = lead_attempt
                events.append(
                    StolenBaseEvent(runner=runner, from_base=from_base, to_base=to_base)
                )
                events.append(
                    RunnerAdvancedEvent(
                        runner=runner,
                        from_base=from_base,
                        to_base=to_base,
                        reason="stolen_base",
                        pitcher=intent.pitcher,
                    )
                )

                from_base, to_base, runner = trail_attempt
                if to_base == SECOND:
                    if self.rng.random() < 0.55:
                        events.append(
                            PutOutEvent(
                                game.pitch_team.current_shortstop,
                                game.pitch_team.current_catcher,
                            )
                        )
                    else:
                        events.append(
                            PutOutEvent(
                                game.pitch_team.current_second_baseman,
                                game.pitch_team.current_catcher,
                            )
                        )
                elif to_base == THIRD:
                    events.append(
                        PutOutEvent(
                            game.pitch_team.current_third_baseman,
                            game.pitch_team.current_catcher,
                        )
                    )
                events.append(
                    CaughtStealingEvent(
                        runner=runner, from_base=from_base, to_base=to_base
                    )
                )
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner, from_base=from_base, reason="caught_stealing"
                    )
                )

            elif result == "both_out":
                # Both out - order doesn't matter
                for from_base, to_base, runner in steal_attempts:
                    # TODO this isn't quite right, we are assuming the catcher threw out both
                    # If the double steal is 2nd and third, this is wrong.
                    if to_base == SECOND:
                        if self.rng.random() < 0.55:
                            events.append(
                                PutOutEvent(
                                    game.pitch_team.current_shortstop,
                                    game.pitch_team.current_catcher,
                                )
                            )
                        else:
                            events.append(
                                PutOutEvent(
                                    game.pitch_team.current_second_baseman,
                                    game.pitch_team.current_catcher,
                                )
                            )
                    elif to_base == THIRD:
                        events.append(
                            PutOutEvent(
                                game.pitch_team.current_third_baseman,
                                game.pitch_team.current_catcher,
                            )
                        )
                    elif to_base == HOME:
                        events.append(
                            PutOutEvent(
                                game.pitch_team.current_catcher, game.current_pitcher
                            )
                        )
                    events.append(
                        CaughtStealingEvent(
                            runner=runner, from_base=from_base, to_base=to_base
                        )
                    )
                    events.append(
                        OutRecordedEvent(
                            reason="caught_stealing", pitcher=intent.pitcher
                        )
                    )
                    events.append(
                        RunnerRemovedEvent(
                            runner=runner,
                            from_base=from_base,
                            reason="caught_stealing",
                        )
                    )
            else:
                raise RuntimeError(f"Unknown result={result} double_steal_probs")

        return events

    def _calculate_throw_out_probability(
        self, arm: int, speed: int, baserunning: int
    ) -> float:
        """Calculate probability of throwing out a runner"""
        # Strong arm and slow runner = higher throw out probability
        base_prob = self.BASE_THROWOUT_PROB
        arm_factor = arm / 50
        runner_factor = 50 / ((speed + baserunning) / 2)
        return base_prob * arm_factor * runner_factor

    def _calculate_error_probability(self, fielding_skill: int) -> float:
        """Calculate probability of fielding error based on skill"""
        # Base error rate around 2-3% for average fielder (skill=50)
        base_error_rate = self.BASE_ERROR_RATE
        # Scale based on skill (lower skill = higher error rate)
        return base_error_rate * (100 - fielding_skill) / 50

    def _is_error(self, events: List[GameEvent]) -> bool:
        """Check if an error occurred."""
        error_event_types = (
            FieldingErrorEvent,
            ThrowingErrorEvent,
        )
        return any(isinstance(event, error_event_types) for event in events)

    def _is_balk(self, events: List[GameEvent]) -> bool:
        """Check if a balk occurred."""
        balk_event_types = (BalkEvent,)
        return any(isinstance(event, balk_event_types) for event in events)

    def _is_walk(self, events: List[GameEvent]) -> bool:
        """Check if a walk occurred."""
        walk_event_types = (
            WalkEvent,
            IBBEvent,
            HitByPitchEvent,
            CatcherInterferenceEvent,
        )
        return any(isinstance(event, walk_event_types) for event in events)

    def _is_wild_pitch_or_passed_ball(self, events: List[GameEvent]) -> bool:
        """Check if wild pitch or passed ball occurred."""
        return any(
            isinstance(event, (WildPitchEvent, PassedBallEvent)) for event in events
        )

    def _is_foul(self, events: List[GameEvent]) -> bool:
        """Check if a foul ball occurred."""
        foul_event_types = (
            FoulStrikeEvent,
            FouledOffThirdStrikeEvent,
            FoulTipCaughtThirdStrikeEvent,
            FoulFlyOutEvent,
        )
        return any(isinstance(event, foul_event_types) for event in events)
