from __future__ import annotations

import logging
from typing import List

from src.game.bases import FIRST, SECOND, THIRD, HOME
from src.game.event import GameEvent
from src.game.events.ball import BallEvent, IllegalPitch
from src.game.events.hbp import HitByPitchEvent
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
    DoubleStealtAttemptEvent,
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
)
from src.game.events.double_play import DoublePlayEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent
from src.game.intents.pick_off import PickOffIntent
from src.game.rules.force_advancement import force_advance_chain


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

    def __init__(self, rng):
        self.rng = rng
        self.logger = logging.getLogger("game.resolver")

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
                pitch_type=intent.pitch_type,
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
            "intentional_walk",
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
        if outcome == "ball":
            events.extend(self._handle_ball(intent, game))

        elif outcome in ("strike", "called_strike", "swinging_strike"):
            events.extend(self._handle_strike_outcome(outcome, intent, game))

        elif outcome == "foul":
            events.extend(self._resolve_foul(intent, game))

        elif outcome == "hit_by_pitch":
            events.extend(self._resolve_walk(intent, game, hbp=True))

        elif outcome == "intentional_walk":
            events.extend(self._resolve_walk(intent, game, intentional=True))

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

        elif outcome == "in_play":
            self.logger.trace("outcome is in_play")
            events.extend(self._resolve_ball_in_play(intent, game))

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
        probs = self.set_probs()
        # TODO adjust probs for player and situation
        return self.random_event(probs)

    def set_probs(self):
        """
        Set the initial probs, for all possible pitch outcomes
        """
        probs = {
            "ball": 10800,
            "foul": 5100,
            "home_run": 280,
            "hit_by_pitch": 60,
            "balk": 0,  # only with runners on base
            "illegal_pitch": 0,  # only with bases empty
            "catcher_interference": 0,
            "intentional_walk": 0,
            "wild_pitch": 0,
            "passed_ball": 0,
            "in_play": 5855,
            "strike": 7100,  # replace with called_strike and swinging_strike
        }
        return probs

    def random_event(self, probs):
        """
        Use a weighted probability. `probs` is a dictionary of events
        and their probability as an integer.

        algorithm: sum up all the integer probabilities. Generate a
        random number between 0 and that sum. Step through the
        dictionary of probabilities subtracting its value from the
        random number until you get it lower than 0. This is guaranteed
        to happen.

        Whichever probability it ends on, return that event.
        """
        if probs is None or probs == {}:
            raise ValueError(f"Probabilities not set: {probs}")
        rand_num = self.rng.random() * sum(probs.values())

        for index, value in enumerate(probs.values()):
            rand_num -= value
            if rand_num <= 0:
                return list(probs)[index]

    def set_in_play_probs(self):
        """
        Set the in play probs, for all possible outcomes
        """
        in_play_probs = {
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
        return in_play_probs

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
        probs = self.set_in_play_probs()
        # TODO adjust in play probs
        outcome = self.random_event(probs)

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

        if outcome in outcome_handlers:
            return outcome_handlers[outcome](intent, game)

        raise RuntimeError(f"Unknown in-play outcome: {outcome}")

    def _resolve_fly_out(self, intent, game) -> list[GameEvent]:
        """Resolve a fly out"""
        return [
            FlyOutEvent(batter=intent.batter),
            OutRecordedEvent(reason="fly_out", pitcher=intent.pitcher),
            PlateAppearanceEndEvent(reason="fly_out", batter=intent.batter),
        ]

    def _resolve_ground_out(self, intent, game) -> list[GameEvent]:
        """Resolve a ground out"""
        return [
            GroundOutEvent(batter=intent.batter),
            OutRecordedEvent(reason="ground_out", pitcher=intent.pitcher),
            PlateAppearanceEndEvent(reason="ground_out", batter=intent.batter),
        ]

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
            if r < self.FOUL_TIP_CAUGHT_PROB:
                self.logger.debug("foul tip strike out ending pa")
                events.extend(
                    [
                        FoulTipCaughtThirdStrikeEvent(),
                        StrikeOutEvent(batter=intent.batter, pitcher=intent.pitcher),
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
        Resolve a single:
        - All runners advance one base
        - Batter to first
        - Plate appearance ends
        """
        events: list[GameEvent] = []

        events.append(SingleEvent(batter=intent.batter, pitcher=intent.pitcher))

        # Advance all runners one base
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="single",
                rbi_batter=intent.batter,
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
        """
        events: list[GameEvent] = []

        events.append(DoubleEvent(batter=intent.batter, pitcher=intent.pitcher))

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
        events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="double_play", pitcher=intent.pitcher))

        if game.bases.runner_on(FIRST):
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(FIRST),
                    from_base=FIRST,
                    reason="double_play",
                )
            )
            # TODO Check if other runners advanced

        # No runner was on first, but we still need a double play
        # try third next.
        elif game.bases.runner_on(THIRD):
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    reason="double_play",
                )
            )
            # TODO Check if other runners advanced

        else:
            # must be a runner on second.
            events.append(
                RunnerRemovedEvent(
                    runner=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="double_play",
                )
            )

        events.append(
            PlateAppearanceEndEvent(reason="double_play", batter=intent.batter)
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
        events.append(
            OutRecordedEvent(reason="fielders_choice", pitcher=intent.pitcher)
        )

        if game.bases.runner_on(THIRD):
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
        - other runners could possibly advance (TODO)
        """
        # Validation
        self._validate_game_state(game, max_outs=2, require_runner_on=THIRD)

        events: list[GameEvent] = []
        # TODO Other runners could also advance possibly

        events.append(SacFlyEvent(batter=intent.batter))
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
        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))
        events.append(OutRecordedEvent(reason="triple_play", pitcher=intent.pitcher))

        if game.bases.is_loaded():
            r = self.rng.random()
            if r < self.TRIPLE_PLAY_FIRST_SECOND_THRESHOLD:
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

        events.append(
            PlateAppearanceEndEvent(reason="triple_play", batter=intent.batter)
        )

        return events


class EnhancedResolver(Resolver):
    """
    Extended Resolver with pre-pitch and concurrent event support.
    """

    # Probability constants for new events
    BASE_PICKOFF_ATTEMPT_PROB = 0.02  # 2% per pitch
    BASE_STEAL_SECOND_PROB = 0.08  # 8% from first
    BASE_STEAL_THIRD_PROB = 0.02  # 2% from second
    BASE_STEAL_HOME_PROB = 0.001  # 0.1% from third

    PICKOFF_SUCCESS_PROB = 0.15  # 15% successful
    PICKOFF_ERROR_PROB = 0.05  # 5% throwing error

    STEAL_SECOND_SUCCESS_PROB = 0.75  # 75% success rate
    STEAL_THIRD_SUCCESS_PROB = 0.80  # 80% success rate
    STEAL_HOME_SUCCESS_PROB = 0.85  # 85% success rate

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
            ):
                # Steals can happen on balls, strikes, fouls, but not walks or ball_in_play
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

        if r < self.PICKOFF_SUCCESS_PROB:
            # Successful pickoff - runner out
            self.logger.debug(f"Successful pickoff at base {base}")
            events.append(
                PickoffSuccessEvent(base=base, runner=runner, pitcher=intent.pitcher)
            )
            events.append(OutRecordedEvent(reason="pickoff", pitcher=intent.pitcher))
            events.append(
                RunnerRemovedEvent(runner=runner, from_base=base, reason="pickoff")
            )

        elif r < self.PICKOFF_SUCCESS_PROB + self.PICKOFF_ERROR_PROB:
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

    # ================================================================
    # CONCURRENT EVENT RESOLUTION (STEALS)
    # ================================================================

    def _resolve_concurrent_events(self, intent: PitchIntent, game) -> List[GameEvent]:
        """
        Resolve events that happen concurrently with the pitch.

        NOTE: Steals should NOT happen on walks, as runners are
        already being force-advanced.

        NOTE: Steals should NOT happen if runners are already being advanced
        by a wild pitch or passed ball.
        """
        events = []

        if game.bases.is_empty:
            return events

        # Check for double steal scenarios
        double_steal_bases = self._get_double_steal_candidates(game)

        if double_steal_bases:
            if self._should_attempt_double_steal(game):
                return self._resolve_double_steal(double_steal_bases, intent, game)

        # Otherwise, check lead runner first (highest base)
        occupied = sorted(game.bases.occupied_map().keys(), reverse=True)

        for base in occupied:
            next_base = base + 1

            # Can't steal if next base occupied
            if next_base <= THIRD and game.bases.runner_on(next_base):
                continue

            if self._should_attempt_steal(base, intent, game):
                return self._resolve_steal_attempt(base, intent, game)

        return events

    def _should_attempt_double_steal(self, game) -> bool:
        """Decide if double steal should be attempted."""

        # Check which scenario
        if game.bases.runner_on(FIRST) and game.bases.runner_on(THIRD):
            # 1st and 3rd is more common (strategic play)
            prob = 0.03  # 3% chance
        else:
            # 1st/2nd or 2nd/3rd - standard double steal
            prob = 0.01  # 1% chance

        # Less likely with 2 outs
        if game.inning.outs == 2:
            prob *= 0.2

        return self.rng.random() < prob

    def _should_attempt_steal(self, from_base: int, intent: PitchIntent, game) -> bool:
        """
        Decide if runner attempts to steal.

        Factors:
        - Runner speed
        - Pitcher delivery time
        - Catcher arm strength
        - Game situation
        - Count
        """
        # Can't steal if next base is occupied (in most cases)
        next_base = from_base + 1
        if next_base <= THIRD and game.bases.runner_on(next_base):
            # Exception: double steal
            if from_base == FIRST and game.bases.runner_on(SECOND):
                # Possible double steal - lower probability
                return self.rng.random() < (self.BASE_STEAL_SECOND_PROB * 0.3)
            return False

        # Base probability by base
        if from_base == FIRST:
            prob = self.BASE_STEAL_SECOND_PROB
        elif from_base == SECOND:
            prob = self.BASE_STEAL_THIRD_PROB
        elif from_base == THIRD:
            prob = self.BASE_STEAL_HOME_PROB
        else:
            return False

        # TODO: Adjust based on:
        # - Runner speed rating
        # - Pitcher delivery time
        # - Catcher pop time/arm strength
        # - Count (more on 3-2, less on 0-2)
        # - Score (more when down, less when up)
        # - Outs (rare with 2 outs)
        # - Pitcher handedness vs runner

        # Simple adjustment: less likely with 2 outs
        if game.inning.outs == 2:
            prob *= 0.5

        return self.rng.random() < prob

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

        # Determine success rate based on target base
        if to_base == SECOND:
            success_prob = self.STEAL_SECOND_SUCCESS_PROB
        elif to_base == THIRD:
            success_prob = self.STEAL_THIRD_SUCCESS_PROB
        elif to_base == HOME:
            success_prob = self.STEAL_HOME_SUCCESS_PROB
        else:
            success_prob = 0.50

        # TODO: Adjust based on runner speed, catcher arm, pitcher delivery

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
            events.append(
                OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
            )
            events.append(
                RunnerRemovedEvent(
                    runner=runner, from_base=from_base, reason="caught_stealing"
                )
            )

        return events

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

        events.append(DoubleStealtAttemptEvent(bases=from_bases))

        # Check if this is 1st and 3rd scenario
        is_first_and_third = FIRST in from_bases and THIRD in from_bases

        # Determine outcome
        r = self.rng.random()

        if is_first_and_third:
            # 1st and 3rd special handling
            first_attempt = next(a for a in steal_attempts if a[0] == FIRST)
            third_attempt = next(a for a in steal_attempts if a[0] == THIRD)

            if r < 0.70:
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

            elif r < 0.85:
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

            elif r < 0.95:
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
                events.append(
                    OutRecordedEvent(reason="caught_stealing", pitcher=intent.pitcher)
                )
                events.append(
                    RunnerRemovedEvent(
                        runner=runner, from_base=from_base, reason="caught_stealing"
                    )
                )

            elif r < 0.99:
                # Runner on 3rd caught, runner on 1st safe
                from_base, to_base, runner = third_attempt
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

            else:
                # Both out
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
            # Standard double steal (1st/2nd or 2nd/3rd)
            # steal_attempts is already sorted in reverse order (lead runner first)

            if r < 0.65:
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

            elif r < 0.90:
                # Lead runner out, trail runner safe
                lead_attempt = steal_attempts[0]  # First in list (highest base)
                trail_attempt = steal_attempts[1]  # Second in list (lowest base)

                from_base, to_base, runner = lead_attempt
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

            elif r < 0.98:
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

            else:
                # Both out - order doesn't matter
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

        return events

    def _get_double_steal_candidates(self, game) -> List[int] | None:
        """
        Get bases for potential double steal.

        When multiple double steals are possible, prioritize:
        1. 2nd and 3rd (most aggressive - runner scores)
        2. 1st and 3rd (strategic play)
        3. 1st and 2nd (most common)
        """
        # Priority 1: 2nd and 3rd (runner on 3rd can score)
        if game.bases.runner_on(SECOND) and game.bases.runner_on(THIRD):
            return [SECOND, THIRD]

        # Priority 2: 1st and 3rd (strategic, only if 2nd empty)
        if game.bases.runner_on(FIRST) and game.bases.runner_on(THIRD):
            if not game.bases.runner_on(SECOND):
                return [FIRST, THIRD]

        # Priority 3: 1st and 2nd (only if 3rd empty)
        if game.bases.runner_on(FIRST) and game.bases.runner_on(SECOND):
            if not game.bases.runner_on(THIRD):
                return [FIRST, SECOND]

        return None

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
