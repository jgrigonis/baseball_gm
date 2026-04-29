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

    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, player_id: str) -> Optional[PlayerInjury]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT player_id, games_remaining FROM player_injuries
               WHERE player_id = %s AND league_id = %s""",
            (player_id, self.league_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return PlayerInjury(
            player_id=row["player_id"], games_remaining=row["games_remaining"]
        )

    def is_injured(self, player_id: str) -> bool:
        injury = self.get(player_id)
        return injury is not None and injury.is_active

    def get_injury_log(self, player_id: str, limit: int = 5) -> list[dict]:
        """Return recent injury log entries for a player, newest first."""
        rows = self.conn.execute(
            """SELECT * FROM player_injury_log
               WHERE player_id = %s ORDER BY injury_date DESC LIMIT %s""",
            (player_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_team_injury_report(self, team_id: str, league_id: str) -> list[dict]:
        """Return injured players for a team with names, ordered by games_remaining DESC."""
        if not team_id:
            return []
        rows = self.conn.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name, pi.games_remaining
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               WHERE pi.games_remaining > 0
                 AND (pi.league_id = %s OR pi.league_id = '')
               ORDER BY pi.games_remaining DESC""",
            (team_id, league_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_for_team(self, team_id: str) -> dict[str, dict]:
        """Return {player_id: {"name": ..., "days": games_remaining, "is_pitcher": bool}} for all active injuries on a team."""
        if not team_id:
            return {}
        rows = self.conn.execute(
            """SELECT pi.player_id, pi.games_remaining,
                      p.first_name || ' ' || p.last_name as name,
                      ps.player_id IS NOT NULL as is_pitcher
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = pi.player_id AND tp.team_id = %s
               LEFT JOIN pitcher_state ps ON ps.player_id = pi.player_id AND ps.league_id = %s
               WHERE pi.games_remaining > 0 AND (pi.league_id = %s OR pi.league_id = '')""",
            (team_id, self.league_id, self.league_id),
        ).fetchall()
        return {
            r["player_id"]: {
                "name": r["name"],
                "days": r["games_remaining"],
                "is_pitcher": bool(r["is_pitcher"]),
            }
            for r in rows
        }

    def get_team_injuries(self, team_id: str) -> dict[str, int]:
        """Return {player_id: games_remaining} for all injured players on a team."""
        if not team_id:
            return {}
        rows = self.conn.execute(
            """SELECT pi.player_id, pi.games_remaining 
                FROM player_injuries pi
                JOIN team_players tp ON tp.player_id = pi.player_id
                WHERE tp.team_id = %s
                AND pi.games_remaining > 0
                AND pi.league_id = %s""",
            (team_id, self.league_id),
        ).fetchall()
        return {r["player_id"]: r["games_remaining"] for r in rows}

    def get_all_injured(self) -> list[PlayerInjury]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT player_id, games_remaining FROM player_injuries
               WHERE games_remaining > 0 AND league_id = %s""",
            (self.league_id,),
        )
        return [
            PlayerInjury(
                player_id=row["player_id"], games_remaining=row["games_remaining"]
            )
            for row in cursor.fetchall()
        ]

    def get_injuries_by_year(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT pil.injury_date, pil.severity, pil.games_missed, pil.activity,
                   s.year as season_year
            FROM player_injury_log pil
            LEFT JOIN seasons s ON s.id = pil.season_id
            WHERE pil.player_id = %s
            ORDER BY pil.injury_date DESC
            """,
            (player_id,),
        ).fetchall()
        return rows

    def count_player_injuries(self, player_id: str, season_id: str) -> int:
        result = self.conn.execute(
            "SELECT COUNT(*) FROM player_injury_log WHERE player_id = %s AND season_id = %s",
            (player_id, season_id),
        ).fetchone()
        return result["count"] if result else 0

    def get_games_missed_in_season(self, player_id: str, season_id: str) -> int:
        result = self.conn.execute(
            "SELECT COALESCE(SUM(games_missed), 0) AS total FROM player_injury_log WHERE player_id = %s AND season_id = %s",
            (player_id, season_id),
        ).fetchone()
        return result["total"] if result else 0

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
        with self.conn.transaction():
            cursor.execute(
                """
                INSERT INTO player_injuries (player_id, league_id, games_remaining)
                VALUES (%s, %s, %s)
                ON CONFLICT(player_id, league_id) DO UPDATE SET
                    games_remaining = excluded.games_remaining
                """,
                (injury.player_id, self.league_id, injury.games_remaining),
            )
            cursor.execute(
                """
                INSERT INTO player_injury_log
                    (player_id, season_id, games_missed, severity, injury_date, activity)
                VALUES (%s, %s, %s, %s, %s, %s)
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
            self.clear_injuries(player_id)
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

    def clear_injuries(self, player_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_injuries WHERE player_id = %s AND league_id = %s",
            (player_id, self.league_id),
        )
        deleted = cursor.rowcount > 0
        # self.conn.commit()
        return deleted

    def clear_all_injuries(self) -> int:
        """Delete all injury rows for this league. Call between seasons."""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM player_injuries WHERE league_id = %s",
            (self.league_id,),
        )
        deleted = cursor.rowcount
        return deleted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self, injury: PlayerInjury) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO player_injuries (player_id, league_id, games_remaining)
            VALUES (%s, %s, %s)
            ON CONFLICT(player_id, league_id) DO UPDATE SET
                games_remaining = excluded.games_remaining
            """,
            (injury.player_id, self.league_id, injury.games_remaining),
        )
