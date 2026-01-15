# src/game/game.py
from __future__ import annotations

from typing import List
import logging

from src.game import inning
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
        rng,
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
        self._queue: List[GameEvent] = []

        # Engine components
        self.intent_generator = intent_generator or IntentGenerator(rng)
        self.resolver = resolver or Resolver(rng)

        # Cursor state
        self.current_batter = None
        self.current_pitcher = None

        # plate appearance info
        self._pa_complete = False
        self._pa_end_reason = None

        # Logging
        self.dbg = logging.TRACE
        self.logger = setup_logger(name="game", level=self.dbg, console_level=self.dbg)

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
            self.step()

    def step(self):
        """
        Execute exactly one atomic event.
        """
        # self.logger.trace("Step")
        if not self._queue:
            intent = self._next_intent()
            self.logger.trace(f"intenet = {intent}")
            events = self._resolve_intent(intent)
            for event in events:
                self.logger.trace(f"event = {event}")
            self._enqueue(events)

        event = self._dequeue()
        self.logger.trace(event)
        # assert not self._pa_complete, f"Event after PA end: {event}"
        event.apply(self)
        # No branching based on game rules inside apply

        self._post_event()

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

    def _enqueue(self, events: list[GameEvent]):
        if not events:
            raise RuntimeError("Resolver returned no events")
        self._queue.extend(events)

    def _dequeue(self) -> GameEvent:
        return self._queue.pop(0)

    # ------------------------------------------------------------------
    # Post-event housekeeping
    # ------------------------------------------------------------------

    def _post_event(self):
        """
        Observe game state after each event and advance structure.
        """
        if self._plate_appearance_over():
            self.logger.trace("_plate_appearance_over")
            self._advance_batter()
            self.count.reset()

        if self._half_inning_over():
            self._end_half_inning()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _plate_appearance_over(self) -> bool:
        """
        Has the current plate appearance completed?
        """
        return self._pa_complete

    def _half_inning_over(self) -> bool:
        return self._would_end_half_inning()

    def _advance_batter(self):
        self.logger.trace("_advance_batter")
        self.current_batter = self._next_batter()
        self._pa_complete = False
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
        self.logger.trace("_mark_plate_appearance_complete")
        self._pa_complete = True
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
        self.logger.info(f"Batting: {self.current_batter}")
        self.current_pitcher = self.pitch_team.current_pitcher()
        self.logger.info(f"Pitching: {self.current_pitcher.name}")
        if not self.is_over():
            self.logger.info(
                {
                    "event": "next_batter",
                    "player": self.current_batter,
                    # "player": self.current_batter,
                    # "stats": f"AB: {self.current_batter.game_stats.batting.at_bats}"
                }
            )
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
