# src/db/repositories/injury_repo.py
"""
src/db/repositories/injury_repo.py

Repository for player injury tracking, scoped per league.

Injury duration table (games missed, not counting the game of injury):
    minor strain / bruise:   3-7
    muscle pull:            10-20
    ligament / sprain:      15-30
    fracture:               30-50
    serious (e.g. ACL):     50-80
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injury severity tiers
# ---------------------------------------------------------------------------

INJURY_TIERS = {
    "minor": (1, 7),
    "moderate": (7, 50),
    "pitcher": (12, 50),
    "severe": (57, 90),
    "surgery": (270, 540),
}


def roll_games_missed(severity: str, rng: random.Random | None = None) -> int:
    lo, hi = INJURY_TIERS.get(severity, INJURY_TIERS["minor"])
    if rng:
        return rng.randint(lo, hi)
    return random.randint(lo, hi)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class PlayerInjury:
    player_id: str
    games_remaining: int

    @property
    def is_active(self) -> bool:
        return self.games_remaining > 0


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class InjuryRepository:
    """Repository for managing player injuries, scoped to a single league."""

    def __init__(self, conn, league_id: str = ""):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PlayerInjury]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT player_id, games_remaining FROM player_injuries
               WHERE player_id = ? AND league_id = ?""",
            (player_id, self.league_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return PlayerInjury(player_id=row[0], games_remaining=row[1])

    def is_injured(self, player_id: str) -> bool:
        injury = self.get(player_id)
        return injury is not None and injury.is_active

    def get_all_injured(self) -> list[PlayerInjury]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT player_id, games_remaining FROM player_injuries
               WHERE games_remaining > 0 AND league_id = ?""",
            (self.league_id,),
        )
        return [
            PlayerInjury(player_id=row[0], games_remaining=row[1])
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def injure(
        self,
        player_id,
        season_id,
        game_date,
        severity="minor",
        activity=None,
        rng=None,
        games=None,
    ):
        games_missed = games if games is not None else roll_games_missed(severity, rng)

        existing = self.get(player_id)
        if existing and existing.games_remaining >= games_missed:
            logger.debug("Player %s already has a worse injury, skipping.", player_id)
            return existing

        injury = PlayerInjury(player_id=player_id, games_remaining=games_missed)

        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO player_injuries (player_id, league_id, games_remaining)
                VALUES (?, ?, ?)
                ON CONFLICT(player_id, league_id) DO UPDATE SET
                    games_remaining = excluded.games_remaining
                """,
                (injury.player_id, self.league_id, injury.games_remaining),
            )
            cursor.execute(
                """
                INSERT INTO player_injury_log
                    (player_id, season_id, games_missed, severity, injury_date, activity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    player_id,
                    season_id,
                    games_missed,
                    severity,
                    (
                        game_date.isoformat()
                        if hasattr(game_date, "isoformat")
                        else game_date
                    ),
                    activity,
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        logger.info(
            "Player %s injured: %s (%d games).", player_id, severity, games_missed
        )
        return injury

    def tick(self, player_id: str) -> Optional[PlayerInjury]:
        injury = self.get(player_id)
        if not injury:
            return None

        injury.games_remaining -= 1

        if injury.games_remaining <= 0:
            self.clear(player_id)
            logger.info("Player %s injury cleared — available to play.", player_id)
            return None

        self._save(injury)
        return injury

    def tick_all(self, player_ids: list[str]) -> dict[str, Optional[PlayerInjury]]:
        results = {}
        for player_id in player_ids:
            if self.is_injured(player_id):
                results[player_id] = self.tick(player_id)
        return results

    def clear(self, player_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_injuries WHERE player_id = ? AND league_id = ?",
            (player_id, self.league_id),
        )
        deleted = cursor.rowcount > 0
        self.conn.commit()
        return deleted

    def clear_all(self) -> int:
        """Delete all injury rows for this league. Call between seasons."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_injuries WHERE league_id = ?",
            (self.league_id,),
        )
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self, injury: PlayerInjury) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO player_injuries (player_id, league_id, games_remaining)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, league_id) DO UPDATE SET
                games_remaining = excluded.games_remaining
            """,
            (injury.player_id, self.league_id, injury.games_remaining),
        )
        self.conn.commit()
