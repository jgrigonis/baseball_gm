from __future__ import annotations

import logging
from typing import List

from src.game.event import GameEvent
from src.game.events.ball import BallEvent
# from src.game.events.hbp import HitByPitchEvent
from src.game.events.noop import NoOpEvent
from src.game.events.pitch import PitchThrownEvent
# from src.game.events.walk import WalkEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent

from src.game.events.strike import StrikeEvent

# from src.game.events.strikeout import StrikeOutEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import OutRecordedEvent
from src.game.bases import FIRST # SECOND, THIRD, HOME

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
            "balk",
            "wild_pitch",
            "passed_ball",
            "home_run",  # We special case this from in_play
            "in_play",  # These are delegated to _resolve_ball_in_play()
        )
        # ------------------------------------------------------------
        # 3. Emit outcome specific events
        # ------------------------------------------------------------
        # TODO add cases for missing outcomes.
        # self.logger.debug(f"outcome = {outcome}")
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
                # events.append(StrikeOutEvent()) # so far it's useless
                events.append(OutRecordedEvent(reason="strikeout"))
                events.append(PlateAppearanceEndEvent(reason="strikeout"))

        elif outcome == "foul":
            if game.count.strikes + 1 >= 3:
                pass  # TODO check for foul tip to catcher
            else:
                # TODO check for caught foul fly ball
                events.append(
                    StrikeEvent(swinging=True)
                )  # TODO Change this for FoulStrikeEvent

        elif outcome == "hit_by_pitch":
            events.extend(self._resolve_walk(intent, game, hbp=True))
            # events.append(HitByPitchEvent())

        elif outcome == "intentional_walk":
            events.extend(self._resolve_walk(intent, game, intentional=True))
            # events.append(WalkEvent()) # TODO Change this for IBBEvent or special case it

        elif outcome == "catcher_interference":
            events.extend(self._resolve_walk(intent, game))  # TODO special case this
            # events.append(WalkEvent()) # TODO Change this for CatcherInterferenceEvent or special case it

        elif outcome == "balk":
            # TODO add a BalkEvent

            pass

        elif outcome == "wild_pitch":
            # TODO add a WildPitchEvent
            pass

        elif outcome == "passed_ball":
            # TODO add a PassedBallEvent
            pass

        elif outcome == "home_run":
            pass  # TODO

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
        # TODO set probs here
        # Base probabilities FAKE

        ball_chance = 0.80

        ball_chance = 0.20
        in_play_chance = 0.40
        foul_chance = 0.1
        hbp_chance = 0.01
        ibb_chance = 0.00
        catcher_interference_chance = 0.001
        balk_chance = 0.01
        wild_pitch_chance = 0.01
        passed_ball_chance = 0.01
        home_run_chance = 0.05
        strike_chance = 0.209

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

    def _resolve_ball_in_play(self, intent, game) -> list[GameEvent]:
        """
        Resolve a ball put into play.

        Must:
        - use rng
        - not mutate game
        - return concrete events
        """
        # TODO set probs here
        events: list[GameEvent] = []

        r = self.rng.random()

        # batter_id = intent.batter_id

        # ------------------------------------------------------------
        # OUT
        # ------------------------------------------------------------
        if r < 0.60:
            # Batter is out
            events.append(OutRecordedEvent(reason="ball_in_play"))
            events.append(PlateAppearanceEndEvent("out"))

            return events

        # ------------------------------------------------------------
        # SINGLE
        # ------------------------------------------------------------
        return self._resolve_single(intent, game)

    # def _force_advance_chain(self, game, starting_base: int, rbi_batter=None):
    #     """
    #     Generate RunnerAdvancedEvents for *forced* runners only.

    #     Definition of "forced":
    #         A runner is forced if a new runner is awarded their current base
    #         and the runner has no legal option to remain.

    #     Properties:
    #         - Forced movement is deterministic (no RNG)
    #         - Forced runners advance exactly one base
    #         - Forced runners form a contiguous chain
    #         - The chain stops at the first empty base
    #         - Event ordering MUST be highest base → lowest base to avoid collisions

    #     Examples:
    #         Walk / HBP:
    #             starting_base = 1
    #             1B occupied → force to 2B
    #             2B occupied → force to 3B
    #             3B occupied → force home

    #         Single:
    #             starting_base = 1
    #             (Only forced if base is already occupied)

    #     Non-goals:
    #         - Does NOT decide voluntary advancement
    #         - Does NOT apply scoring logic
    #         - Does NOT end the plate appearance

    #     Events are returned in SAFE application order:
    #     highest base → lowest base.

    #     starting_base: the base the batter will occupy (usually FIRST).
    #     """
    #     forward = []

    #     base = starting_base
    #     while base <= THIRD:
    #         runner = game.bases.runner_on(base)
    #         if not runner:
    #             break

    #         forward.append(
    #             RunnerAdvancedEvent(
    #                 runner_id=runner,
    #                 from_base=base,
    #                 to_base=base + 1,
    #                 reason="force",
    #                 rbi_batter_id=rbi_batter,
    #             )
    #         )
    #         base += 1

    #     # Apply highest base first to avoid collisions
    #     return list(reversed(forward))

    def _resolve_walk(self, intent, game, hbp=False, intentional=False):
        self.logger.trace("Entering _resolve_walk")
        self.logger.debug(game.bases)

        events = []

        if hbp:
            reason = "intentional_hit_by_pitch" if intentional else "hit_by_pitch"
        else:
            reason = "intentional_walk" if intentional else "walk"

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
