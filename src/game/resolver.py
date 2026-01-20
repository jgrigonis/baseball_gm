from __future__ import annotations

import logging
from typing import List

from src.game.event import GameEvent
from src.game.events.ball import BallEvent, IllegalPitch

from src.game.events.hbp import HitByPitchEvent
from src.game.events.noop import NoOpEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.events.balk import BalkEvent
from src.game.events.wild_pitch import WildPitchEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.hits import SingleEvent, HomeRunEvent

from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent

from src.game.events.strike import (
    StrikeEvent,
    FoulStrikeEvent,
    FoulThirdStrikeEvent,
    FoulTipThirdStrikeEvent,
)

from src.game.events.strikeout import StrikeOutEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import OutRecordedEvent
from src.game.bases import FIRST  # SECOND, THIRD, HOME

from src.game.rules.force_advancement import force_advance_chain
from src.game.events.runners import RunnerAdvancedEvent


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

    def resolve(self, intent: GameIntent, game) -> List[GameEvent]:
        """
        Resolve an intent into one or more GameEvents.

        Must always return at least one event.
        """
        if isinstance(intent, PitchIntent):
            return self._resolve_pitch(intent, game)

        # Unknown intent: advance nothing but keep clock moving
        # return [NoOpEvent()]
        # for now this is an error
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
        # sanity check
        assert outcome in (
            "ball",
            "strike",  # We allow strikes with no detail for now
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
            "home_run",  # We special case this from in_play
            "in_play",  # These are delegated to _resolve_ball_in_play()
        )
        # ------------------------------------------------------------
        # 3. Emit outcome specific events
        # ------------------------------------------------------------
        if outcome == "ball":
            events.append(BallEvent())
            if game.count.balls + 1 >= 4:
                events.extend(self._resolve_walk(intent, game))

        elif outcome in ("strike", "called_strike", "swinging_strike"):
            if outcome == "strike":
                events.append(StrikeEvent())
            if outcome == "called_strike":
                events.append(StrikeEvent(swinging=False))
            if outcome == "swinging_strike":
                events.append(StrikeEvent(swinging=True))
            if game.count.strikes + 1 >= 3:
                self.logger.debug("strike out ending pa")
                events.append(StrikeOutEvent())
                events.append(OutRecordedEvent(reason="strikeout"))
                events.append(PlateAppearanceEndEvent(reason="strikeout"))

        elif outcome == "foul":
            events.extend(self._resolve_foul(intent, game))

        elif outcome == "hit_by_pitch":
            events.extend(self._resolve_walk(intent, game, hbp=True))

        elif outcome == "intentional_walk":
            events.extend(self._resolve_walk(intent, game, intentional=True))

        elif outcome == "catcher_interference":
            events.extend(self._resolve_walk(intent, game, catcher_interference=True))

        elif outcome == "illegal_pitch":
            events.append(IllegalPitch())
            events.append(BallEvent())
            if game.count.balls + 1 >= 4:
                events.extend(self._resolve_walk(intent, game))

        elif outcome == "balk":
            if game.bases.is_empty:
                self.logger.trace("Balk called with no runners on.")
            else:
                events.append(BalkEvent())

        elif outcome == "wild_pitch":
            if game.bases.is_empty:
                # This should never actually happen
                self.logger.trace("Wild Pitch occured with no runners on.")
            else:
                events.append(WildPitchEvent())

        elif outcome == "passed_ball":
            if game.bases.is_empty:
                # This should never actually happen
                # It would only matter on a third strike, and we have that
                # covered elsewhere
                self.logger.trace("Passed Ball occured with no runners on.")
            else:
                events.append(PassedBallEvent())

        elif outcome == "home_run":
            self.logger.trace("home_run")
            events.extend(self._resolve_home_run(intent, game))

        elif outcome == "in_play":
            self.logger.trace("outcome is in_play")
            events.extend(self._resolve_ball_in_play(intent, game))

        else:
            # self.logger.debug("NoOp triggered")
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
        # TODO set pitch outcome probs here
        # Base probabilities FAKE

        # ball_chance = 0.80

        ball_chance = 0.20  # was 0.2
        in_play_chance = 0.40  # was 0.4
        foul_chance = 0.01  # was 0.01
        hbp_chance = 0.01
        ibb_chance = 0.00
        catcher_interference_chance = 0.001
        illegal_pitch_chance = 0.001
        balk_chance = 0.01
        wild_pitch_chance = 0.01
        passed_ball_chance = 0.01
        home_run_chance = 0.05
        strike_chance = 0.208

        r = self.rng.random()

        sum = ball_chance
        if r < sum:
            return "ball"
        sum += in_play_chance
        if r < sum:
            return "in_play"
        sum += foul_chance
        if r < sum:
            return "foul"
        sum += hbp_chance
        if r < sum:
            return "hit_by_pitch"
        sum += ibb_chance
        if r < sum:
            return "intentional_walk"
        sum += catcher_interference_chance
        if r < sum:
            return "catcher_interference"
        sum += illegal_pitch_chance
        if r < sum:
            return "illegal_pitch"
        sum += balk_chance
        if r < sum:
            return "balk"
        sum += wild_pitch_chance
        if r < sum:
            return "wild_pitch"
        sum += passed_ball_chance
        if r < sum:
            return "passed_ball"
        sum += home_run_chance
        if r < sum:
            return "home_run"
        if r > strike_chance:
            return "strike"

    def _resolve_home_run(self, intent, game) -> list[GameEvent]:
        """
        Resolve a home run.

        Score all the runners on base.
        Score the batter.
        """
        events: list[GameEvent] = []

        events.append(HomeRunEvent(batter_id=intent.batter_id))

        for base in (3, 2, 1):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=4,
                    reason="home_run",
                    rbi_batter_id=intent.batter_id,
                )
            )
        # Batter to home
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=4,
                reason="home_run",
            )
        )

        # End the plate appearance
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
            r = self.rng.random()  # TODO check for foul tip BETTER
            if r < 0.05:  # 0.05
                self.logger.debug("foul tip strike out ending pa")
                events.append(FoulTipThirdStrikeEvent())
                events.append(StrikeOutEvent())
                events.append(OutRecordedEvent(reason="strikeout"))
                events.append(PlateAppearanceEndEvent(reason="strikeout"))
            else:
                events.append(FoulThirdStrikeEvent())

        else:  # less than 2 strikes
            r = self.rng.random()
            # TODO check for foul fly ball BETTER
            if r < 0.05:
                events.extend(self._resolve_ball_in_play(intent, game, foul=True))
            else:
                events.append(FoulStrikeEvent(swinging=True))
        
        return events

    def _resolve_ball_in_play(self, intent, game, foul=False) -> list[GameEvent]:
        """
        Resolve a ball put into play.

        Must:
        - use rng
        - not mutate game
        - return concrete events
        """
        # TODO set in play probs here
        events: list[GameEvent] = []

        r = self.rng.random()

        # ------------------------------------------------------------
        # OUT
        # ------------------------------------------------------------
        if foul:
            # batter flew out with a foul ball.
            events.append(OutRecordedEvent(reason="foul_fly_out"))
            events.append(PlateAppearanceEndEvent("out"))

            return events

        if r < 0.60:  # TODO this is very fake
            # Batter is out
            events.append(OutRecordedEvent(reason="ball_in_play"))
            events.append(PlateAppearanceEndEvent("out"))

            return events

        # ------------------------------------------------------------
        # SINGLE
        # ------------------------------------------------------------
        return self._resolve_single(intent, game)

    def _resolve_walk(
        self, intent, game, hbp=False, intentional=False, catcher_interference=False
    ):
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
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=FIRST,
                reason=reason,
            )
        )
        self.logger.trace("Ending PA in _resolve_walk")
        # End PA (and only ends PA)
        events.append(PlateAppearanceEndEvent(reason))

        return events

    def _resolve_single(self, intent, game):
        """
        Resolve a single:
        - All runners advance one base
        - Batter to first
        - Plate appearance ends
        """
        # TODO Add Baserunner moving logic here
        events = []

        events.append(SingleEvent(batter_id=intent.batter_id))
        # Advance existing runners (3 -> home, 2 -> 3, 1 -> 2)
        for base in (3, 2, 1):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=base + 1,
                    reason="single",
                    rbi_batter_id=intent.batter_id,
                )
            )

        # Batter to first
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=1,
                reason="single",
            )
        )

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("single"))

        return events
