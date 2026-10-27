# src/db/repositories/injury_repo.py
"""
src/db/repositories/injury_repo.py

Repository for player injury tracking, scoped per league.

Injuries are measured in calendar days, not games. An injury stores the
date the player is available again (return_date), so off days, the gap
before the playoffs and the offseason all count toward recovery.

A player injured on day D who misses N days sits out D+1 .. D+N and is
available again on D+N+1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import logging
import random

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injury severity tiers (days missed)
# ---------------------------------------------------------------------------

INJURY_TIERS = {
    "minor": (1, 7),
    "moderate": (7, 50),
    "pitcher": (12, 50),
    "severe": (57, 90),
    "surgery": (270, 540),
}


def roll_days_missed(severity: str, rng: random.Random | None = None) -> int:
    lo, hi = INJURY_TIERS.get(severity, INJURY_TIERS["minor"])
    if rng:
        return rng.randint(lo, hi)
    return random.randint(lo, hi)


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class PlayerInjury:
    player_id: str
    return_date: date
    days_remaining: int

    @property
    def is_active(self) -> bool:
        return self.days_remaining > 0


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

    def current_date(self) -> date:
        """
        The league's "today" for injury purposes: the day after the most
        recent completed game in this league. Before any game is played,
        the first scheduled game date; failing that, the real date.
        """
        row = self.conn.execute(
            """SELECT MAX(g.game_date) FILTER (WHERE g.completed = 1) AS last_played,
                      MIN(g.game_date) FILTER (WHERE g.completed = 0) AS next_up
               FROM games g
               JOIN league_seasons ls ON ls.season_id = g.season_id
               WHERE ls.league_id = %s""",
            (self.league_id,),
        ).fetchone()
        if row and row["last_played"]:
            return _to_date(row["last_played"]) + timedelta(days=1)
        if row and row["next_up"]:
            return _to_date(row["next_up"])
        return date.today()

    def _as_of(self, as_of) -> str:
        return (_to_date(as_of) if as_of else self.current_date()).isoformat()

    def get(self, player_id: str, as_of=None) -> PlayerInjury | None:
        as_of = self._as_of(as_of)
        row = self.conn.execute(
            """SELECT player_id, return_date,
                      (return_date::date - %s::date) AS days_remaining
               FROM player_injuries
               WHERE player_id = %s AND league_id = %s
                 AND return_date IS NOT NULL""",
            (as_of, player_id, self.league_id),
        ).fetchone()
        if not row:
            return None
        return PlayerInjury(
            player_id=row["player_id"],
            return_date=_to_date(row["return_date"]),
            days_remaining=max(0, row["days_remaining"]),
        )

    def is_injured(self, player_id: str, as_of=None) -> bool:
        injury = self.get(player_id, as_of)
        return injury is not None and injury.is_active

    def get_injured_ids(self, player_ids, as_of) -> set[str]:
        """Return the subset of player_ids who are still injured on as_of."""
        if not player_ids:
            return set()
        rows = self.conn.execute(
            """SELECT player_id FROM player_injuries
               WHERE league_id = %s AND player_id = ANY(%s)
                 AND return_date::date > %s::date""",
            (self.league_id, list(player_ids), self._as_of(as_of)),
        ).fetchall()
        return {r["player_id"] for r in rows}

    def get_injury_log(self, player_id: str, limit: int = 5) -> list[dict]:
        """Return recent injury log entries for a player, newest first."""
        rows = self.conn.execute(
            """SELECT * FROM player_injury_log
               WHERE player_id = %s ORDER BY injury_date DESC LIMIT %s""",
            (player_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_team_injury_report(
        self, team_id: str, league_id: str, as_of=None
    ) -> list[dict]:
        """Return injured players for a team with names, ordered by days_remaining DESC."""
        if not team_id:
            return []
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name,
                      (pi.return_date::date - %s::date) AS days_remaining
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               WHERE pi.return_date::date > %s::date
                 AND (pi.league_id = %s OR pi.league_id = '')
               ORDER BY days_remaining DESC""",
            (as_of, team_id, as_of, league_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_for_team(self, team_id: str, as_of=None) -> dict[str, dict]:
        """Return {player_id: {"name", "days", "position", "outs", "ab"}} for all
        active injuries on a team. outs and ab are the player's regular-season
        pitching outs and at-bats in the league's current season (0 if none)."""
        if not team_id:
            return {}
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT pi.player_id,
                      (pi.return_date::date - %s::date) AS days_remaining,
                      p.first_name || ' ' || p.last_name as name,
                      p.position,
                      COALESCE(st.outs, 0) AS outs,
                      COALESCE(st.ab, 0) AS ab
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = pi.player_id AND tp.team_id = %s
               LEFT JOIN (
                   SELECT pss.player_id, SUM(pss.pitch_outs) AS outs,
                          SUM(pss.bat_ab) AS ab
                   FROM player_season_stats pss
                   WHERE NOT pss.is_postseason
                     AND pss.season_id = (
                         SELECT s.id FROM seasons s
                         JOIN league_seasons ls ON ls.season_id = s.id
                         WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1)
                   GROUP BY pss.player_id
               ) st ON st.player_id = pi.player_id
               WHERE pi.return_date::date > %s::date
                 AND (pi.league_id = %s OR pi.league_id = '')""",
            (as_of, team_id, self.league_id, as_of, self.league_id),
        ).fetchall()
        return {
            r["player_id"]: {
                "name": r["name"],
                "days": r["days_remaining"],
                "position": r["position"],
                "outs": int(r["outs"]),
                "ab": int(r["ab"]),
            }
            for r in rows
        }

    def get_team_injuries(self, team_id: str, as_of=None) -> dict[str, int]:
        """Return {player_id: days_remaining} for all injured players on a team."""
        if not team_id:
            return {}
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT pi.player_id,
                      (pi.return_date::date - %s::date) AS days_remaining
                FROM player_injuries pi
                JOIN team_players tp ON tp.player_id = pi.player_id
                WHERE tp.team_id = %s
                AND pi.return_date::date > %s::date
                AND pi.league_id = %s""",
            (as_of, team_id, as_of, self.league_id),
        ).fetchall()
        return {r["player_id"]: r["days_remaining"] for r in rows}

    def get_all_injured(self, as_of=None) -> list[PlayerInjury]:
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT player_id, return_date,
                      (return_date::date - %s::date) AS days_remaining
               FROM player_injuries
               WHERE return_date::date > %s::date AND league_id = %s""",
            (as_of, as_of, self.league_id),
        ).fetchall()
        return [
            PlayerInjury(
                player_id=row["player_id"],
                return_date=_to_date(row["return_date"]),
                days_remaining=row["days_remaining"],
            )
            for row in rows
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

    def get_season_injuries(
        self, season_id: str, team_id: str | None = None
    ) -> list[dict]:
        """Every injury suffered in a season, oldest first, with the player's
        name and position and the team the player was on when hurt. Limit to one
        team with `team_id`."""
        rows = self.conn.execute(
            """
            SELECT pil.player_id, p.first_name || ' ' || p.last_name AS name,
                   p.last_name || ' ' || p.first_name AS sort_name, p.position,
                   pil.team_id, t.city, t.mascot,
                   pil.injury_date, pil.severity, pil.activity,
                   pil.games_missed AS days_missed
            FROM player_injury_log pil
            JOIN players p ON p.id = pil.player_id
            LEFT JOIN teams t ON t.id = pil.team_id
            WHERE pil.season_id = %s
              AND (%s::text IS NULL OR pil.team_id = %s)
            ORDER BY pil.injury_date, pil.id
            """,
            (season_id, team_id, team_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_player_injuries(self, player_id: str, season_id: str) -> int:
        result = self.conn.execute(
            "SELECT COUNT(*) FROM player_injury_log WHERE player_id = %s AND season_id = %s",
            (player_id, season_id),
        ).fetchone()
        return result["count"] if result else 0

    def get_days_missed_in_season(self, player_id: str, season_id: str) -> int:
        """Total days missed to injuries suffered this season (log column is games_missed)."""
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
        days=None,
        team_id=None,
    ):
        """
        Record an injury suffered on game_date. The player misses `days`
        calendar days (rolled from the severity tier if not given) and is
        available again the day after that. `team_id` is the team the
        player was hurt playing for.
        """
        injury_day = _to_date(game_date)
        days_missed = days if days is not None else roll_days_missed(severity, rng)
        return_date = injury_day + timedelta(days=days_missed + 1)

        existing = self.get(player_id, as_of=injury_day + timedelta(days=1))
        if existing and existing.return_date >= return_date:
            logger.debug("Player %s already has a worse injury, skipping.", player_id)
            return existing

        injury = PlayerInjury(
            player_id=player_id,
            return_date=return_date,
            days_remaining=days_missed,
        )

        cursor = self.conn.cursor()
        with self.conn.transaction():
            # games_remaining is legacy (pre day-based injuries); it now just
            # records the length of the current injury in days.
            cursor.execute(
                """
                INSERT INTO player_injuries
                    (player_id, league_id, games_remaining, return_date)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(player_id, league_id) DO UPDATE SET
                    games_remaining = excluded.games_remaining,
                    return_date = excluded.return_date
                """,
                (player_id, self.league_id, days_missed, return_date.isoformat()),
            )
            cursor.execute(
                """
                INSERT INTO player_injury_log
                    (player_id, season_id, team_id, games_missed, severity,
                     injury_date, activity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    player_id,
                    season_id,
                    team_id,
                    days_missed,
                    severity,
                    injury_day.isoformat(),
                    activity,
                ),
            )

        logger.info(
            "Player %s injured: %s (%d days, back %s).",
            player_id,
            severity,
            days_missed,
            return_date.isoformat(),
        )
        return injury

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
