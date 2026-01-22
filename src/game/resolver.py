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
from src.game.events.strike import (
    StrikeEvent,
    FoulStrikeEvent,
    FouledOffThirdStrikeEvent,
    FoulTipCaughtThirdStrikeEvent,
)
from src.game.events.strikeout import StrikeOutEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import OutRecordedEvent
from src.game.events.double_play import DoublePlayEvent
from src.game.events.triple_play import TriplePlayEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent
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
                pitcher_id=intent.pitcher_id,
                batter_id=intent.batter_id,
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
            events.extend(self._handle_strike_outcome(outcome, game))

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
            events.extend(self._handle_wild_pitch(game))

        elif outcome == "passed_ball":
            events.extend(self._handle_passed_ball(game))

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
        if max_outs is not None and game.outs >= max_outs:
            raise RuntimeError(
                f"Play cannot occur with {game.outs} outs (max: {max_outs - 1})"
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
        self, game, bases: tuple, advancement: int, reason: str, rbi_batter_id=None
    ) -> list[GameEvent]:
        """Advance runners on specified bases by advancement amount (capped at HOME)"""
        events = []
        for base in bases:
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=min(base + advancement, HOME),
                    reason=reason,
                    rbi_batter_id=rbi_batter_id,
                )
            )
        return events

    def _advance_batter_to_base(
        self, batter_id: str, to_base: int, reason: str
    ) -> RunnerAdvancedEvent:
        """Create event for batter advancing to a base"""
        return RunnerAdvancedEvent(
            runner_id=batter_id, from_base=None, to_base=to_base, reason=reason
        )

    def _handle_ball(self, intent, game) -> list[GameEvent]:
        """Handle a ball being called"""
        events = [BallEvent()]
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game))
        return events

    def _handle_strike_outcome(self, outcome: str, game) -> list[GameEvent]:
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
                    StrikeOutEvent(),
                    OutRecordedEvent(reason="strikeout"),
                    PlateAppearanceEndEvent(reason="strikeout"),
                ]
            )

        return events

    def _handle_illegal_pitch(self, intent, game) -> list[GameEvent]:
        """Handle an illegal pitch"""
        events = [IllegalPitch(), BallEvent()]
        if game.count.balls + 1 >= 4:
            events.extend(self._resolve_walk(intent, game))
        return events

    def _handle_balk(self, game) -> list[GameEvent]:
        """Handle a balk"""
        if game.bases.is_empty:
            self.logger.trace("Balk called with no runners on.")
            return []
        return [BalkEvent()]

    def _handle_wild_pitch(self, game) -> list[GameEvent]:
        """Handle a wild pitch"""
        if game.bases.is_empty:
            self.logger.trace("Wild Pitch occurred with no runners on.")
            return []
        # TODO Are we properly calling a ball here?
        # TODO if it walks, do we double advance runners?
        return [WildPitchEvent()]

    def _handle_passed_ball(self, game) -> list[GameEvent]:
        """Handle a passed ball"""
        if game.bases.is_empty:
            self.logger.trace("Passed Ball occurred with no runners on.")
            return []
        # TODO Are we properly calling a ball here?
        # TODO if it walks, do we double advance runners?
        return [PassedBallEvent()]

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
            OutRecordedEvent(reason="fly_out"),
            PlateAppearanceEndEvent("fly_out"),
        ]

    def _resolve_ground_out(self, intent, game) -> list[GameEvent]:
        """Resolve a ground out"""
        return [
            OutRecordedEvent(reason="ground_out"),
            PlateAppearanceEndEvent("ground_out"),
        ]

    def _resolve_home_run(self, intent, game) -> list[GameEvent]:
        """
        Resolve a home run.

        Score all the runners on base.
        Score the batter.
        """
        events: list[GameEvent] = []

        events.append(HomeRunEvent(batter_id=intent.batter_id))

        # Score all runners
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=HOME,  # Will be capped at HOME
                reason="home_run",
                rbi_batter_id=intent.batter_id,
            )
        )

        # Batter scores
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=HOME,
                reason="home_run",
            )
        )

        events.append(PlateAppearanceEndEvent("home_run"))

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
                        StrikeOutEvent(),
                        OutRecordedEvent(reason="strikeout"),
                        PlateAppearanceEndEvent(reason="strikeout"),
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
            OutRecordedEvent(reason="foul_fly_out"),
            PlateAppearanceEndEvent("out"),
        ]

    def _resolve_walk(
        self, intent, game, hbp=False, intentional=False, catcher_interference=False
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
            events.append(HitByPitchEvent(batter_id=intent.batter_id))
        else:
            if intentional:
                reason = "intentional_walk"
                events.append(IBBEvent(batter_id=intent.batter_id))
            elif catcher_interference:
                reason = "catcher_interference"
                events.append(CatcherInterferenceEvent(batter_id=intent.batter_id))
            else:
                reason = "walk"
                events.append(WalkEvent(batter_id=intent.batter_id))

        # Force existing runners
        occupied = game.bases.occupied_map()

        forced = force_advance_chain(
            occupied_bases=occupied,
            start_base=1,
            rbi_batter_id=intent.batter_id,
        )
        for f in forced:
            events.append(
                RunnerAdvancedEvent(
                    runner_id=f.runner_id,
                    from_base=f.from_base,
                    to_base=f.to_base,
                    reason=f.reason,
                    rbi_batter_id=f.rbi_batter_id,
                )
            )

        # Award batter first base
        events.append(self._advance_batter_to_base(intent.batter_id, FIRST, reason))

        self.logger.trace("Ending PA in _resolve_walk")
        events.append(PlateAppearanceEndEvent(reason))

        return events

    def _resolve_single(self, intent, game):
        """
        Resolve a single:
        - All runners advance one base
        - Batter to first
        - Plate appearance ends
        """
        events: list[GameEvent] = []

        events.append(SingleEvent(batter_id=intent.batter_id))

        # Advance all runners one base
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="single",
                rbi_batter_id=intent.batter_id,
            )
        )

        # Batter to first
        events.append(self._advance_batter_to_base(intent.batter_id, FIRST, "single"))

        events.append(PlateAppearanceEndEvent("single"))

        return events

    def _resolve_double(self, intent, game):
        """
        Resolve a double:
        - All runners advance two bases by default
        - Batter to second
        - Plate appearance ends
        """
        events: list[GameEvent] = []

        events.append(DoubleEvent(batter_id=intent.batter_id))

        # Advance all runners two bases
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=2,
                reason="double",
                rbi_batter_id=intent.batter_id,
            )
        )

        # Batter to second
        events.append(self._advance_batter_to_base(intent.batter_id, SECOND, "double"))

        events.append(PlateAppearanceEndEvent("double"))

        return events

    def _resolve_triple(self, intent, game):
        """
        Resolve a triple:
        - All runners score by default
        - Batter to third
        - Plate appearance ends
        """
        events: list[GameEvent] = []

        events.append(TripleEvent(batter_id=intent.batter_id))

        # All runners score (advancement to HOME)
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=HOME,  # Will be capped at HOME
                reason="triple",
                rbi_batter_id=intent.batter_id,
            )
        )

        # Batter to third
        events.append(self._advance_batter_to_base(intent.batter_id, THIRD, "triple"))

        events.append(PlateAppearanceEndEvent("triple"))

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

        events.append(DoublePlayEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="double_play"))
        events.append(OutRecordedEvent(reason="double_play"))

        if game.bases.runner_on(FIRST):
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(FIRST),
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
                    runner_id=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    reason="double_play",
                )
            )
            # TODO Check if other runners advanced

        else:
            # must be a runner on second.
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="double_play",
                )
            )

        events.append(PlateAppearanceEndEvent("double_play"))

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

        events.append(FieldersChoiceEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="fielders_choice"))

        if game.bases.runner_on(THIRD):
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(THIRD),
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
                    runner_id=game.bases.runner_on(FIRST),
                    from_base=FIRST,
                    reason="fielders_choice",
                )
            )
            # Advance runner on second if present
            runner = game.bases.runner_on(SECOND)
            if runner:
                events.append(
                    RunnerAdvancedEvent(
                        runner_id=runner,
                        from_base=SECOND,
                        to_base=THIRD,
                        reason="fielders_choice",
                    )
                )

        else:
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="fielders_choice",
                )
            )

        # Batter to first
        events.append(
            self._advance_batter_to_base(intent.batter_id, FIRST, "fielders_choice")
        )
        events.append(PlateAppearanceEndEvent("fielders_choice"))

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

        events.append(SacBuntEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="sac_bunt"))

        # Advance all runners one base
        events.extend(
            self._advance_all_runners(
                game,
                (THIRD, SECOND, FIRST),
                advancement=1,
                reason="sac_bunt",
                rbi_batter_id=intent.batter_id,
            )
        )

        events.append(PlateAppearanceEndEvent("sac_bunt"))

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

        events.append(SacFlyEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="sac_fly"))

        runner = game.bases.runner_on(THIRD)
        events.append(
            RunnerAdvancedEvent(
                runner_id=runner,
                from_base=THIRD,
                to_base=HOME,
                reason="sac_fly",
                rbi_batter_id=intent.batter_id,
            )
        )

        events.append(PlateAppearanceEndEvent("sac_fly"))

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
        if game.outs > 0:
            raise RuntimeError(
                "Triple play cannot occur with outs already in the inning."
            )
        if len(game.bases.occupied_map()) < 2:
            raise RuntimeError(
                "Triple play cannot occur without at least 2 runners on base."
            )

        events: list[GameEvent] = []

        events.append(TriplePlayEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="triple_play"))
        events.append(OutRecordedEvent(reason="triple_play"))
        events.append(OutRecordedEvent(reason="triple_play"))

        if game.bases.is_loaded():
            r = self.rng.random()
            if r < self.TRIPLE_PLAY_FIRST_SECOND_THRESHOLD:
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
            elif r < self.TRIPLE_PLAY_FIRST_THIRD_THRESHOLD:
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )
            else:
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
        else:  # bases not loaded, must be two runners on, and both are out
            if game.bases.runner_on(FIRST):
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(FIRST),
                        from_base=FIRST,
                        reason="triple_play",
                    )
                )
            if game.bases.runner_on(SECOND):
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(SECOND),
                        from_base=SECOND,
                        reason="triple_play",
                    )
                )
            if game.bases.runner_on(THIRD):
                events.append(
                    RunnerRemovedEvent(
                        runner_id=game.bases.runner_on(THIRD),
                        from_base=THIRD,
                        reason="triple_play",
                    )
                )

        events.append(PlateAppearanceEndEvent("triple_play"))

        return events
