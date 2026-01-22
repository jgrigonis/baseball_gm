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
from src.game.events.hits import SingleEvent, DoubleEvent, TripleEvent, HomeRunEvent
from src.game.events.fielders_choice import FieldersChoiceEvent
from src.game.events.walk import WalkEvent, IBBEvent, CatcherInterferenceEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent
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
from src.game.bases import FIRST, SECOND, THIRD, HOME

from src.game.rules.force_advancement import force_advance_chain
from src.game.events.runners import RunnerAdvancedEvent, RunnerRemovedEvent


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
        self.logger.trace(outcome)
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
                # TODO Are we properly calling a ball here?
                # TODO if it walks, do we double advance runners?
                events.append(WildPitchEvent())

        elif outcome == "passed_ball":
            if game.bases.is_empty:
                # This should never actually happen
                # It would only matter on a third strike, and we have that
                # covered elsewhere
                self.logger.trace("Passed Ball occured with no runners on.")
            else:
                # TODO Are we properly calling a ball here?
                # TODO if it walks, do we double advance runners?
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
        self.logger.trace("_determine_pitch_outcome")
        probs = self.set_probs()
        # TODO adjust probs for player and situation
        return self.random_event(probs)

    def set_probs(self):
        """
        Set the initial probs, for all possible pitch outcomes
        """
        probs = {
            "ball": 10800,  # yes
            "foul": 5100,  # yes
            "home_run": 280,  # yes
            "hit_by_pitch": 60,  # yes
            "balk": 0,  # yes only with runners on base
            "illegal_pitch": 0,  # yes only with bases empty
            "catcher_interference": 0,  # yes
            "intentional_walk": 0,  # yes
            "wild_pitch": 0,  # yes
            "passed_ball": 0,  # yes
            "in_play": 5855,  # in play
            "strike": 7100,  # replace with the 2 below
            # add called_strike
            # sdd swinging_strike
        }
        return probs

        # TODO figure out these:
        # "caught_stealing": 0, # concurrent event
        # "caught_stealing_third": 0, # concurrent event
        # "caught_stealing_home": 0, # concurrent event
        # "steal": 0, # concurrent event
        # "steal_third": 0, # concurrent event
        # "steal_home": 0, # concurrent event

        # "picked_off": 0, # pre-pitch
        # "picked_off_second": 0, # pre-pitch
        # "picked_off_third": 0, # pre-pitch

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
        # print(rand_num)
        # print(sum(probs.values()))
        for index, value in enumerate(probs.values()):
            rand_num -= value
            if rand_num <= 0:
                return list(probs)[index]

    def set_in_play_probs(self):
        """
        Set the in play probs, for all possible outcomes
        """
        in_play_probs = {
            "fly_out": 2050,  # in_play_chance
            "ground_out": 2050,  # in_play_chance
            "single": 1350,  # in_play_chance
            "double": 360,  # in_play_chance
            "triple": 45,  # in_play_chance
            "double_play": 0,  # in_play_chance
            "fielders_choice": 0,  # in_play_chance
            "sac_fly": 0,  # in_play_chance
            "sac_bunt": 0,  # in_play_chance
            "triple_play": 0,  # in_play_chance
        }
        return in_play_probs

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

        assert outcome in (
            "fly_out",
            "ground_out",
            "single",
            "double",
            "triple",
            "double_play",
            "fielders_choice",
            "sac_fly",
            "sac_bunt",
            "triple_play",
        )

        events: list[GameEvent] = []

        # ------------------------------------------------------------
        # FLY OUT
        # ------------------------------------------------------------
        if outcome == "fly_out":
            events.append(OutRecordedEvent(reason="fly_out"))
            events.append(PlateAppearanceEndEvent("fly_out"))
        if outcome == "ground_out":
            # this should be extremely rare with a runner on first
            events.append(OutRecordedEvent(reason="ground_out"))
            events.append(PlateAppearanceEndEvent("ground_out"))
        if outcome == "single":
            return self._resolve_single(intent, game)
        if outcome == "double":
            return self._resolve_double(intent, game)
        if outcome == "triple":
            return self._resolve_triple(intent, game)
        if outcome == "double_play":
            return self._resolve_double_play(intent, game)
        if outcome == "fielders_choice":
            return self._resolve_fielders_choice(intent, game)
        if outcome == "sac_fly":
            return self._resolve_sac_fly(intent, game)
        if outcome == "sac_bunt":
            return self._resolve_sac_bunt(intent, game)
        if outcome == "triple_play":
            return self._resolve_triple_play(intent, game)

        return events

    def _resolve_home_run(self, intent, game) -> list[GameEvent]:
        """
        Resolve a home run.

        Score all the runners on base.
        Score the batter.
        """
        events: list[GameEvent] = []

        events.append(HomeRunEvent(batter_id=intent.batter_id))

        for base in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=HOME,
                    reason="home_run",
                    rbi_batter_id=intent.batter_id,
                )
            )
        # Batter to home
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=HOME,
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
                events.append(FoulTipCaughtThirdStrikeEvent())
                events.append(StrikeOutEvent())
                events.append(OutRecordedEvent(reason="strikeout"))
                events.append(PlateAppearanceEndEvent(reason="strikeout"))
            elif r < 0.95:
                events.append(FouledOffThirdStrikeEvent())
            else:  # TODO check for fly out better
                events.extend(self._resolve_fly_out_foul(intent, game))

        else:  # less than 2 strikes
            r = self.rng.random()
            # TODO check for foul fly ball BETTER
            if r < 0.05:
                events.extend(self._resolve_fly_out_foul(intent, game))
            else:
                events.append(FoulStrikeEvent(swinging=True))

        return events

    def _resolve_fly_out_foul(self, intent, game):
        """
        Simply resolves a fly out foul, can happen with 2 strikes or less.
        """
        # events = []
        events: list[GameEvent] = []
        events.append(OutRecordedEvent(reason="foul_fly_out"))
        events.append(PlateAppearanceEndEvent("out"))
        return events

    def _resolve_walk(
        self, intent, game, hbp=False, intentional=False, catcher_interference=False
    ):
        """
        Reolves a walk. Will deal with hit py pitch, and intentional walks as well.

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
        # events = []
        events: list[GameEvent] = []

        events.append(SingleEvent(batter_id=intent.batter_id))
        # Advance existing runners (3 -> home, 2 -> 3, 1 -> 2)
        for base in (THIRD, SECOND, FIRST):
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
                to_base=FIRST,
                reason="single",
            )
        )

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("single"))

        return events

    def _resolve_double(self, intent, game):
        """
        Resolve a double:
        - All runners advance two bases by default
        - Batter to second
        - Plate appearance ends
        """
        # TODO Add Baserunner moving logic here
        events: list[GameEvent] = []

        events.append(DoubleEvent(batter_id=intent.batter_id))
        # Advance existing runners (3 -> home, 2 -> 3, 1 -> 2)
        for base in (3, 2, 1):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=base + 2,
                    reason="double",
                    rbi_batter_id=intent.batter_id,
                )
            )

        # Batter to second
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=SECOND,
                reason="double",
            )
        )

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("double"))

        return events

    def _resolve_triple(self, intent, game):
        """
        Resolve a triple:
        - All runners score by default
        - Batter to third
        - Plate appearance ends
        """
        # TODO Add Baserunner moving logic here
        events: list[GameEvent] = []

        events.append(TripleEvent(batter_id=intent.batter_id))
        # Advance existing runners (3 -> home, 2 -> 3, 1 -> 2)
        for base in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=HOME,
                    reason="triple",
                    rbi_batter_id=intent.batter_id,
                )
            )

        # Batter to second
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=THIRD,
                reason="triple",
            )
        )

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("triple"))

        return events

    def _resolve_double_play(self, intent, game):
        """
        Should raise an error if no runner on base.

        Resolve a double play:
        - Default runner on first is out via force
        - And batter/runner is out

        - Other runners could advance and potentially score
        - If no outs

        - If no runner on first, another runner must be put out
        - plus the batter/runner or another runner

        - There must be two outs.

        - Plate appearance ends
        """
        # TODO Add Baserunner moving logic to this function
        # Validate: cannot have 2 outs
        if game.outs >= 2:
            raise RuntimeError("Double play cannot occur with 2 outs")
        # Validate: must have at least one runner on base
        if game.bases.is_empty:
            raise RuntimeError("Double play cannot occur with no runners on base")
        events: list[GameEvent] = []

        events.append(DoublePlayEvent(batter_id=intent.batter_id))

        if game.bases.runner_on(FIRST):
            events.append(OutRecordedEvent(reason="double_play"))
            events.append(OutRecordedEvent(reason="double_play"))
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
            events.append(OutRecordedEvent(reason="double_play"))
            events.append(OutRecordedEvent(reason="double_play"))
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(THIRD),
                    from_base=THIRD,
                    reason="double_play",
                )
            )
            # TODO Check if other runners advanced, this assumes the double play put out the runner on third and the batter.
        
        else:
            # must be a runner on second.
            # No other runners
            events.append(OutRecordedEvent(reason="double_play"))
            events.append(OutRecordedEvent(reason="double_play"))
            events.append(
                RunnerRemovedEvent(
                    runner_id=game.bases.runner_on(SECOND),
                    from_base=SECOND,
                    reason="double_play",
                )
            )

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("double_play"))

        return events

    def _resolve_fielders_choice(self, intent, game):
        """
        Fielder's choice can result in no outs.

        The official scorers must deem that had the fielder chosen to throw to
        1B, that it would have been a routine play.

        If they try to get the lead runner instead and fail, then it would be
        a fielder's choice.

        I see this more often at home. Fielder throws home to prevent the run,
        but the runner is safe. The play at 2B is often just as routine, unless
        it's a bunt.

        A run scores on a fielder's choice when the defense prioritizes getting
        another runner, and that play allows the run to cross the plate before
        the defense gets an out on the batter or another forced runner.

        The default is one out, but there doesn't need to be an out necessarily

        There should be an error if no runners on

        algorithm:
        - pick one runner to put out, move all other runners forward one base.
        - If there is a runner on third, pick that one
        - Else pick the runner on first
        - Else the runner on second
        - Place the batter on first
        """
        # Validate: cannot have 2 outs
        if game.outs >= 2:
            raise RuntimeError("Fielder's choice cannot occur with 2 outs")

        # Validate: must have at least one runner on base
        if game.bases.is_empty:
            raise RuntimeError("Fielder's choice cannot occur with no runners on base")
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
            for base in (SECOND, FIRST):
                runner = game.bases.runner_on(base)
                if not runner:
                    continue

                events.append(
                    RunnerAdvancedEvent(
                        runner_id=runner,
                        from_base=base,
                        to_base=base + 1,
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
            RunnerAdvancedEvent(
                runner_id=intent.batter_id,
                from_base=None,
                to_base=FIRST,
                reason="fielders_choice",
            )
        )
        events.append(PlateAppearanceEndEvent("fielders_choice"))
        return events

    def _resolve_sac_bunt(self, intent, game):
        """
        A sac bunt must be a bunt. There can't be 2 outs.
        
        Should return an error if called with 2 outs or with
        no runner on

        - move a runner from 1st to 2nd if no other runners
        - move a runner from 2nd to third if no other runners
        - score a runner from 3rd if no other runners
        - all runners should advance if multiple.
        - put out the batter
        """
        # Validate: cannot have 2 outs
        if game.outs >= 2:
            raise RuntimeError("Sacrifice bunt cannot occur with 2 outs")
        
        # Validate: must have at least one runner on base
        if game.bases.is_empty:
            raise RuntimeError("Sacrifice bunt cannot occur with no runners on base")

        events: list[GameEvent] = []

        events.append(SacBuntEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="sac_bunt"))

        # Single base runner
        for base in (THIRD, SECOND, FIRST):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=base + 1,
                    reason="sac_bunt",
                    rbi_batter_id=intent.batter_id,
                )
            )
        
        events.append(PlateAppearanceEndEvent("sac_bunt"))

        return events

    def _resolve_sac_fly(self, intent, game):
        """
        A sac fly must result in a score. There can't be 2 outs.

        Should return an error if called with 2 outs or with
        no runner on third

        - score the runner on third
        - put out the batter
        - other runs could possibly advance (TODO)
        """
        # Validate: cannot have 2 outs
        if game.outs >= 2:
            raise RuntimeError("Sacrifice fly cannot occur with 2 outs")
        
        # Validate: must have runner on third (already present but move it up)
        runner = game.bases.runner_on(THIRD)
        if not runner:
            raise RuntimeError("Sacrifice fly requires a runner on third base")

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
        if game.outs > 0:
            raise RuntimeError("Triple play cannot occur with outs already in the inning.")
        if len(game.bases.occupied_map()) < 2:
            raise RuntimeError("Triple play cannot occur without at least 2 runners on base.")
        events: list[GameEvent] = []

        events.append(TriplePlayEvent(batter_id=intent.batter_id))
        events.append(OutRecordedEvent(reason="triple_play"))
        events.append(OutRecordedEvent(reason="triple_play"))
        events.append(OutRecordedEvent(reason="triple_play"))

        if game.bases.is_loaded():
            r = self.rng.random()
            if r < 0.3333:
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
            elif r < 0.6666:
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

        # End the plate appearance
        events.append(PlateAppearanceEndEvent("triple_play"))

        return events
