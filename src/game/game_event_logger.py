# src/game/game_event_logger.py
"""
src/game/game_event_logger.py

Logs auditable game events to the game_events table.
Passed into Game.__init__ as an optional dependency — None = silent.

Usage in play_season.py:
    event_logger = GameEventLogger(conn, game_id=game_info["game_id"])
    game = Game(home_team, away_team, ..., event_logger=event_logger)
"""

from __future__ import annotations
import json
import logging

import psycopg

_log = logging.getLogger("game_event_logger")
from src.db.repositories.game_event_repo import GameEventRepository


def closer_entry_label(score_diff: int, save_situation: bool) -> str:
    """Why the closer came in: a save chance, or a tie or lead worth protecting."""
    if save_situation:
        return f"in for save (up {score_diff})"
    if score_diff == 0:
        return "in, tie game (high leverage)"
    return f"in, high leverage (up {score_diff})"


class GameEventLogger:
    """Writes structured game events to the game_events table."""

    def __init__(self, conn, game_id: str):
        self.conn = conn
        self.game_id = game_id
        self._inning: int | None = None
        self._half: str | None = None
        # TODO should we put the GameEventRepository in init?

    def set_context(self, inning: int, half: str) -> None:
        """Update current inning context. Called as innings advance."""
        self._inning = inning
        self._half = half  # 'top' or 'bottom'

    # ------------------------------------------------------------------
    # Public event writers
    # ------------------------------------------------------------------

    def lineup_set(self, team_id: str, slots: list[dict]) -> None:
        """Record the starting lineup.
        slots: [{"batting_order": 1, "player_id": ..., "name": ..., "position": ...}]
        """
        self._insert(
            team_id=team_id,
            event_type="lineup_set",
            inning=None,
            half=None,
            reason=f"{len(slots)} players",
            detail=json.dumps(slots),
        )

    def pitcher_start(self, team_id: str, player_id: str, name: str) -> None:
        """Record the starting pitcher."""
        self._insert(
            team_id=team_id,
            event_type="pitcher_start",
            inning=None,
            half=None,
            player_id=player_id,
            reason=f"{name} starts",
        )

    def pitching_change(
        self,
        team_id: str,
        incoming_id: str,
        incoming_name: str,
        outgoing_id: str,
        outgoing_name: str,
        reason: str,
        detail: str,
    ) -> None:
        """Record a pitching change and why it was made."""
        self._insert(
            team_id=team_id,
            event_type="pitching_change",
            player_id=incoming_id,
            player_id_2=outgoing_id,
            reason=f"{incoming_name} replaces {outgoing_name} — {reason}",
            detail=detail,
        )

    def closer_called(
        self,
        team_id: str,
        player_id: str,
        name: str,
        outgoing_id: str,
        outgoing_name: str,
        score_diff: int,
        save_situation: bool = True,
    ) -> None:
        """Record the closer coming in, for a save or a high-leverage spot."""
        self._insert(
            team_id=team_id,
            event_type="closer_called",
            player_id=player_id,
            player_id_2=outgoing_id,
            reason=f"{name} {closer_entry_label(score_diff, save_situation)}"
            f" — replaces {outgoing_name}",
        )

    def injury(
        self,
        team_id: str,
        player_id: str,
        name: str,
        severity: str,
        activity: str,
    ) -> None:
        """Record an in-game injury."""
        self._insert(
            team_id=team_id,
            event_type="injury",
            player_id=player_id,
            reason=f"{name} — {severity} ({activity})",
        )

    def substitution(
        self,
        team_id: str,
        incoming_id: str,
        incoming_name: str,
        outgoing_id: str,
        outgoing_name: str,
        position: str,
    ) -> None:
        """Record a position player substitution."""
        self._insert(
            team_id=team_id,
            event_type="substitution",
            player_id=incoming_id,
            player_id_2=outgoing_id,
            reason=f"{incoming_name} replaces {outgoing_name} at {position}",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _insert(
        self,
        team_id: str,
        event_type: str,
        inning: int | None = None,
        half: str | None = None,
        player_id: str | None = None,
        player_id_2: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
    ) -> None:
        inning = inning if inning is not None else self._inning
        half = half if half is not None else self._half
        try:
            # Savepoint: a failed insert is undone on its own without
            # committing or discarding the rest of the game's writes.
            with self.conn.transaction():
                ger = GameEventRepository(self.conn)
                ger.insert_game_event(
                    game_id=self.game_id,
                    inning=inning,
                    half=half,
                    team_id=team_id,
                    event_type=event_type,
                    player_id=player_id,
                    player_id_2=player_id_2,
                    reason=reason,
                    detail=detail,
                )
        except psycopg.Error:
            # Never let a failed event insert crash a game; the savepoint
            # above has already undone it.
            _log.warning("Failed to log event %s", event_type, exc_info=True)
