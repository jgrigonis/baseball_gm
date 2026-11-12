# src/game/play_log.py
"""
The game's play-by-play: one entry per plate appearance (what the batter
did, who fielded it, who scored, the steals and wild pitches along the way),
never pitch by pitch. Game feeds it every event it applies (Game.step) and
closes each half-inning; play_season saves the list as one JSON row per game
(game_plays), kept only for the league's current season.

An entry is kept small and holds no text: the panel words it
(src/api/view_models/play_by_play.py), so the wording can change later.

    i, t   inning and top (True) or bottom
    b      batter's name, None when the half ended mid plate appearance
           (a runner caught stealing or picked off for the third out)
    r      how the plate appearance ended: single, strikeout, fly_out, ...
    f      fielders on the out: [putout position, assist position or None]
    e      position charged with an error on the play
    d      [runner, base] for a runner doubled off on a liner or thrown out
           tagging up on a fly ball (an air double play)
    s      names of runners who scored
    n      other things during it: [kind, name, base] for steals, caught
           stealing, pickoffs (pitcher's "po", catcher's "cpo"), pickoff
           errors ("poe"/"cpoe", base is the position charged), wild
           pitches, passed balls, balks, extra bases on errors
    o      outs after it
    sc     score after it, [away, home]
    g      game_events rows written before it, so substitutions and
           pitching changes fall in the right place
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.game.events.balk import BalkEvent
from src.game.events.error import (
    ErrorChargedEvent,
    FieldingErrorEvent,
    OutfielderThrowingErrorEvent,
    RunnerAdvancedOnErrorEvent,
    ThrowingErrorEvent,
)
from src.game.events.out import AirDoublePlayEvent, PutOutEvent
from src.game.events.passed_ball import PassedBallEvent
from src.game.events.pick_off import (
    CatcherPickoffErrorEvent,
    CatcherPickoffSuccessEvent,
    PickoffErrorEvent,
    PickoffSuccessEvent,
)
from src.game.events.plate_appearance import PlateAppearanceEndEvent
from src.game.events.scoring import RunScoredEvent
from src.game.events.steal import CaughtStealingEvent, StolenBaseEvent
from src.game.events.wild_pitch import WildPitchEvent

if TYPE_CHECKING:
    from src.game.game import Game


def short_name(p) -> str:
    first = (p.first_name or "").strip()
    return f"{first[0]}. {p.last_name}" if first else p.last_name


class PlayLog:
    def __init__(self) -> None:
        self.plays: list[dict] = []
        self._reset()

    def _reset(self) -> None:
        self._fielders: list | None = None
        self._error: str | None = None
        self._scored: list[str] = []
        self._notes: list[list] = []
        self._doubled: list | None = None

    def see(self, event, game: Game) -> None:
        """Note one applied event."""
        if isinstance(event, RunScoredEvent):
            self._scored.append(short_name(event.runner))
        elif isinstance(event, PutOutEvent):
            if self._fielders is None:
                self._fielders = [
                    event.fielder.current_position,
                    event.assist.current_position if event.assist else None,
                ]
        elif isinstance(
            event, (FieldingErrorEvent, ThrowingErrorEvent, ErrorChargedEvent)
        ):
            self._error = event.fielder.current_position
        elif isinstance(event, AirDoublePlayEvent):
            self._doubled = [short_name(event.runner), event.base]
        elif isinstance(event, StolenBaseEvent):
            self._notes.append(["sb", short_name(event.runner), event.to_base])
        elif isinstance(event, CaughtStealingEvent):
            self._notes.append(["cs", short_name(event.runner), event.to_base])
        elif isinstance(event, PickoffSuccessEvent):
            self._notes.append(["po", short_name(event.runner), event.base])
        elif isinstance(event, PickoffErrorEvent):
            who = event.fielder or event.pitcher
            self._notes.append(["poe", None, who.current_position])
        elif isinstance(event, CatcherPickoffSuccessEvent):
            self._notes.append(["cpo", short_name(event.runner), event.base])
        elif isinstance(event, CatcherPickoffErrorEvent):
            self._notes.append(["cpoe", None, event.fielder.current_position])
        elif isinstance(event, WildPitchEvent):
            self._notes.append(["wp", None, None])
        elif isinstance(event, PassedBallEvent):
            self._notes.append(["pb", None, None])
        elif isinstance(event, BalkEvent):
            self._notes.append(["bk", None, None])
        elif isinstance(
            event, (RunnerAdvancedOnErrorEvent, OutfielderThrowingErrorEvent)
        ):
            self._notes.append(
                ["xe", short_name(event.runner), event.fielder.current_position]
            )
        elif isinstance(event, PlateAppearanceEndEvent):
            self._add(game, short_name(event.batter), event.reason)

    def end_half(self, game: Game) -> None:
        """The half-inning (or game) is over: keep anything that happened
        after the last plate appearance ended (a runner caught stealing for
        the third out, say)."""
        if self._notes or self._scored:
            # A walk-off stops the game the moment the run scores, before
            # the plate appearance's end event comes off the queue.
            pending = next(
                (e for e in game._queue if isinstance(e, PlateAppearanceEndEvent)),
                None,
            )
            if pending:
                self._add(game, short_name(pending.batter), pending.reason)
            else:
                self._add(game, None, None)
        self._reset()

    def _add(self, game: Game, batter: str | None, reason: str | None) -> None:
        play = {
            "i": game.inning.number,
            "t": game.inning.top,
            "b": batter,
            "r": reason,
            "o": min(game.inning.outs, 3),
            "sc": [game.score.away, game.score.home],
            "g": game.event_logger.count if game.event_logger else 0,
        }
        if self._fielders and reason not in ("strikeout",):
            play["f"] = self._fielders
        if self._error:
            play["e"] = self._error
        if self._doubled:
            play["d"] = self._doubled
        if self._scored:
            play["s"] = self._scored
        if self._notes:
            play["n"] = self._notes
        self.plays.append(play)
        self._reset()
