# src/game/game.py
from __future__ import annotations

from collections import deque

# from typing import List
import logging
import random

from src.game.inning import Inning
from src.game.count import Count
from src.game.bases import Bases
from src.game.score import Score
from src.game.event import GameEvent
from src.game.intent import GameIntent
from src.game.intent_generator import IntentGenerator
from src.game.resolver import Resolver
from src.util.logger import setup_logger


class Game:
    """
    Orchestrates game flow.

    Game owns:
    - game state
    - event queue
    - step loop

    Game does NOT:
    - decide outcomes
    - enforce baseball rules
    """

    def __init__(
        self,
        home_team,
        away_team,
        *,
        rng: random.Random | None = None,
        log_level: int | None = None,
        intent_generator: IntentGenerator | None = None,
        resolver: Resolver | None = None,
    ):
        # Teams
        self.home = home_team
        self.away = away_team
        self.bat_team = self.away
        self.pitch_team = self.home

        # Core state
        self.inning = Inning()
        self.count = Count()
        self.bases = Bases()
        self.score = Score()

        # Event pipeline
        self._queue: deque[GameEvent] = deque[GameEvent]()

        # Random
        self.rng = rng or random.Random()
        # Engine components
        self.intent_generator = intent_generator or IntentGenerator(self.rng)
        self.resolver = resolver or Resolver(self.rng)

        # Cursor state
        self.current_batter = None
        self.current_pitcher = None

        # plate appearance info
        self._plate_appearance_complete = False
        self._pa_end_reason = None

        # Logging
        self.log_level = log_level or logging.INFO
        self.logger = setup_logger(name="game", level=self.log_level, console_level=self.log_level)
        self.logger.setLevel(self.log_level)
        self.pauses = False

        # Stat setup
        self._init_game_stats()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play(self):
        """Run until game end condition."""
        if not self.home.has_lineup or not self.away.has_lineup:
            raise RuntimeError("Both teams must have lineups before play()")
        self._sync_players()
        self.logger.info("Play Ball!")
        while not self.is_over():
            if self.pauses:
                input("Press enter to continue")
            self.step()
            self._post_event()

    # def step_pitch(self) -> list[GameEvent]:
    #     """
    #     Process exactly one pitch for the current batter.
    #     Returns the list of events generated.
    #     The plate appearance may or may not end.
    #     """
    #     if self.is_over():
    #         return []

    #     events: list[GameEvent] = []

    #     intent = self._next_intent()

    #     # # Get the next pitch intent for the current batter
    #     # if not self._intent_queue:
    #     #     # Optionally, generate the intent automatically (AI pitch)
    #     #     self._intent_queue.append(self.current_batter_pitch_intent())

    #     # intent = self._intent_queue.popleft()
    #     new_events = self.resolver.resolve(intent, self) or []

    #     for e in new_events:
    #         e.apply(self)
    #         events.append(e)

    #     # Update plate appearance state if ended
    #     if any(isinstance(e, PlateAppearanceEndEvent) for e in new_events):
    #         self._plate_appearance_over = True

    #     return events

    """
    Resolver produces initial events
    Events may produce follow-up events
    Follow-ups must execute before anything already queued
    No game logic branches inside step()
    PlateAppearanceEndEvent must be terminal

    “Apply exactly one event, but allow that event to 
    expand into more events that must happen now.”
    """

    def step(self):
        # 1. If there are events, apply exactly one
        if self._queue:
            event = self._dequeue()
            self.logger.trace(f"[STEP] apply → {event}")
            followups = event.apply(self) or []
            if followups:
                self._enqueueleft(followups)
            # self._post_event()
            return

        # This is dead code, never gets here
        # # 2. No queued events → maybe create a new intent
        # if self._plate_appearance_complete:
        #     self.logger.info(f"_plate_appearance_complete")
        #     return  # PA finished; wait for game-level transition

        intent = self._next_intent()
        self.logger.trace(f"[STEP] intent → {intent}")
        events = self._resolve_intent(intent)
        self._enqueue(events)

    # ------------------------------------------------------------------
    # Post-event housekeeping
    # ------------------------------------------------------------------

    def _post_event(self):
        """
        Observe game state after each event and advance structure.
        """
        if self._plate_appearance_complete and self._queue:
            raise RuntimeError("PlateAppearanceEndEvent fired with pending events")

        if self._plate_appearance_complete:
            # self.logger.trace("_plate_appearance_complete")
            self._advance_batter()
            self.count.reset()

        if self._half_inning_over():
            self._end_half_inning()

    # def step(self):
    #     """
    #     Execute exactly one atomic event.
    #     """

    #     if not self._queue:
    #         intent = self._next_intent()
    #         self.logger.trace(f"[STEP] intent → {intent}")

    #         events = self._resolve_intent(intent)
    #         if not events:
    #             raise RuntimeError("Resolver returned no events")

    #         self._enqueue(events)

    #     event = self._dequeue()
    #     self.logger.trace(f"[STEP] apply → {event}")

    #     followups = event.apply(self) or []

    #     if followups:
    #         self._enqueueleft(followups)

    #     self._post_event()

    # ------------------------------------------------------------------
    # Intent / Resolution
    # ------------------------------------------------------------------

    def _next_intent(self) -> GameIntent:
        return self.intent_generator.next_intent(self)

    def _resolve_intent(self, intent: GameIntent) -> list[GameEvent]:
        return self.resolver.resolve(intent, self)

    # ------------------------------------------------------------------
    # Event queue
    # ------------------------------------------------------------------

    """
    Event queue invariants:

    - Queue is FIFO
    - Resolver enqueues events to the BACK only
    - Events may enqueue follow-up events to the FRONT
    - step() executes exactly one event
    """

    def _enqueue(self, events: list[GameEvent]):
        if not events:
            raise RuntimeError("Resolver returned no events")
        self._queue.extend(events)

    def _dequeue(self) -> GameEvent:
        return self._queue.popleft()

    def _enqueueleft(self, events):
        """
        Enqueue events to the front of the queue.
        Preserves execution order.
        """
        if not events:
            return

        if isinstance(events, list):
            for event in reversed(events):
                self._queue.appendleft(event)
        else:
            self._queue.appendleft(events)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _half_inning_over(self) -> bool:
        return self._would_end_half_inning()

    def _advance_batter(self):
        self.logger.trace("_advance_batter")
        self.current_batter = self._next_batter()
        self._plate_appearance_complete = False
        self._pa_end_reason = None

    def _end_half_inning(self):
        self.logger.debug("End half inning")
        self.inning.increment()
        self.bases.clear()
        self.count.reset()
        self._queue.clear()
        self.logger.debug(self.inning)
        self.logger.debug(self.score)

    def is_over(self) -> bool:
        # self.logger.trace("Is Over?")
        self.logger.trace(f"inning = {self.inning}")
        if self.inning.number < 9:
            return False
        if self.inning.number == 9:
            if self.inning.bottom:
                if self.score.home > self.score.away:
                    self.logger.trace(
                        "Game ends because home team is winning in the bottom of the 9th"
                    )
                    return True
        if self.inning.number > 9:
            if self.inning.bottom:
                if self.score.home > self.score.away:
                    self.logger.trace(
                        "Game ends because home team is winning in the bottom of extra innings"
                    )
                    return True
            if self.score.home != self.score.away:
                self.logger.trace(
                    "Game ends because the score is not tied and 9 or more innings complete"
                )
                return True
        return False
        # raise NotImplementedError
        # return False  # stub

    def _mark_plate_appearance_complete(self, reason: str):
        # self.logger.trace("_mark_plate_appearance_complete")
        self._plate_appearance_complete = True
        self._pa_end_reason = reason

    def _init_game_stats(self):
        """
        This will clear out the current game stats for every player on both teams
        """
        for player in self.away.players + self.home.players:
            player.init_game_stats()

    def _sync_players(self):
        """Sync the current batter and pitcher."""
        self.logger.debug("Syncing players")
        self.current_batter = self.bat_team.current_batter
        self.logger.info(f"Batting: {self.current_batter.player.name}")
        self.current_pitcher = self.pitch_team.current_pitcher
        self.logger.info(f"Pitching: {self.current_pitcher.name}")

    def _would_end_half_inning(self) -> bool:
        """
        Determine whether the current half-inning should end.

        Pure query:
        - No mutation
        - No events
        """
        return self.inning.outs >= 3

    def _next_batter(self) -> None:
        # self.logger.trace("_next_batter")
        self.logger.trace(f"prev batter={self.current_batter}")
        next = self.bat_team.next_batter()
        self.logger.trace(f"next batter={next.player.name}")
        return next

    def _debug_queue(self, prefix=""):
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        contents = [e.label() for e in self._queue]
        self.logger.debug(f"{prefix}QUEUE = {contents}")
