from __future__ import annotations

import logging
from typing import List

from src.game.event import GameEvent
from src.game.events.ball import BallEvent
from src.game.events.noop import NoOpEvent
from src.game.events.pitch import PitchThrownEvent
from src.game.intent import GameIntent
from src.game.intents.pitch import PitchIntent

from src.game.events.strike import StrikeEvent
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.out import OutRecordedEvent
from src.game.events.run import RunScoredEvent
from src.game.events.bases import RunnerAdvancedEvent


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
                # pitch_type=intent.pitch_type, # might break
            )
        )

        # ------------------------------------------------------------
        # 2. Determine outcome (pure decision)
        # ------------------------------------------------------------
        outcome = self._determine_pitch_outcome(intent, game)
        # sanity check
        assert outcome in ("ball", "strike", "in_play")
        # ------------------------------------------------------------
        # 3. Emit outcome specific events
        # ------------------------------------------------------------
        # self.logger.debug(f"outcome = {outcome}")
        if outcome == "ball":
            events.append(BallEvent())

        elif outcome == "strike":
            events.append(StrikeEvent())

        elif outcome == "in_play":
            events.extend(self._resolve_ball_in_play(intent, game))

        else:
            # self.logger.debug("NoOp triggered")
            return [NoOpEvent()]

        # # ------------------------------------------------------------
        # # 3. Terminal checks (using PRE-event state + hypothetical event)
        # # ------------------------------------------------------------
        # if self._would_end_plate_appearance(outcome, game):
        #     result = self._derive_plate_appearance_result(outcome, game)
        #     self.logger.trace(f"result = {result}")
        #     events.append(PlateAppearanceEndEvent(result))

        #     if result in ("strikeout", "out"):
        #         events.append(OutRecordedEvent(result))

        return events

    # Never called
    # def _would_end_plate_appearance(self, outcome: str, game) -> bool:
    #     if outcome == "strike" and game.count.strikes == 2:
    #         return True
    #     if outcome == "ball" and game.count.balls == 3:
    #         return True
    #     if outcome == "in_play":
    #         return True
    #     return False

    def _derive_plate_appearance_result(self, outcome: str, game) -> str:
        if outcome == "strike":
            return "strikeout"
        if outcome == "ball":
            return "walk"
        return "ball_in_play"

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
        # Base probabilities
        ball_chance = 0.25
        strike_chance = 0.65
        # in_play_chance = 0.40 # whatever is left out of 1.0

        r = self.rng.random()

        if r < ball_chance:
            return "ball"
        elif r < ball_chance + strike_chance:
            return "strike"
        else:
            return "in_play"

    # def _resolve_ball_in_play(self, intent, game):
    #     outcome = self._determine_contact_outcome(...)

    #     if outcome == "single":
    #         return self._resolve_single(intent, game)
    #     if outcome == "out":
    #         return self._resolve_out(intent, game)

    #     raise RuntimeError("Unhandled ball-in-play outcome")

    def _resolve_ball_in_play(self, intent, game) -> list[GameEvent]:
        """
        Resolve a ball put into play.

        Must:
        - use rng
        - not mutate game
        - return concrete events
        """
        events: list[GameEvent] = []

        r = self.rng.random()

        # batter_id = intent.batter_id

        # ------------------------------------------------------------
        # OUT
        # ------------------------------------------------------------
        if r < 0.60:
            # Batter is out
            events.append(PlateAppearanceEndEvent("out"))
            events.append(OutRecordedEvent(reason="ball_in_play"))

            return events

        # ------------------------------------------------------------
        # SINGLE
        # ------------------------------------------------------------
        return self._resolve_single(intent, game)

    def _force_advance_chain(self, game, starting_base: int):
        """
        Generate RunnerAdvancedEvents for forced runners,
        starting at a given base and moving upward.
        """
        events = []

        for base in (3, 2, 1):
            if base < starting_base:
                continue

            runner = game.bases.runner_on(base)
            if not runner:
                continue

            to_base = base + 1
            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner, from_base=base, to_base=to_base, reason="force"
                )
            )

        return events

    def _resolve_walk(self, intent, game):
        events = []

        # Force existing runners
        events.extend(self._force_advance_chain(game, starting_base=1))

        # Batter to first
        events.append(
            RunnerAdvancedEvent(
                runner_id=intent.batter_id, from_base=None, to_base=1, reason="walk"
            )
        )

        events.append(PlateAppearanceEndEvent("walk"))

        return events

    def _resolve_single(self, intent, game):
        events = []

        # Advance existing runners
        for base in (3, 2, 1):
            runner = game.bases.runner_on(base)
            if not runner:
                continue

            to_base = base + 1

            events.append(
                RunnerAdvancedEvent(
                    runner_id=runner,
                    from_base=base,
                    to_base=to_base,
                    reason="single",
                )
            )

            if to_base == 4:
                events.append(
                    RunScoredEvent(
                        runner_id=runner,
                        rbi_batter_id=intent.batter_id,
                        reason="single",
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

        events.append(PlateAppearanceEndEvent("single"))

        return events

    # This one was missing scoring
    # def _resolve_single(self, intent, game):
    #     """
    #     Resolve a single:
    #     - All runners advance one base
    #     - Batter to first
    #     - Plate appearance ends
    #     """
    #     events = []

    #     # Advance existing runners (3 -> home, 2 -> 3, 1 -> 2)
    #     for base in (3, 2, 1):
    #         runner = game.bases.runner_on(base)
    #         if not runner:
    #             continue

    #         events.append(
    #             RunnerAdvancedEvent(
    #                 runner_id=runner,
    #                 from_base=base,
    #                 to_base=base + 1,
    #                 reason="single",
    #             )
    #         )

    #     # Batter to first
    #     events.append(
    #         RunnerAdvancedEvent(
    #             runner_id=intent.batter_id,
    #             from_base=None,
    #             to_base=1,
    #             reason="single",
    #         )
    #     )

    #     # End the plate appearance
    #     events.append(
    #         PlateAppearanceEndEvent("single")
    #     )

    #     return events
