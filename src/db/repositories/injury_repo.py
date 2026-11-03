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

from psycopg.types.json import Jsonb

# Severity tiers and day rolls live with the injury catalog; INJURY_TIERS and
# roll_days_missed are re-exported here for code that imports them from here.
from src.player.injury_types import (  # noqa: F401
    INJURY_TIERS,
    roll_days_missed,
    roll_lasting,
    roll_rust,
    rust_days_to_clear,
    rust_left,
)
from src.player.positions import is_pitcher

logger = logging.getLogger(__name__)


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
    injury_type: str | None = None

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
            """SELECT player_id, return_date, injury_type,
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
            injury_type=row["injury_type"],
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
            """SELECT p.id as player_id, p.first_name, p.last_name, pi.injury_type,
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
        """Return {player_id: {"name", "days", "injury_type", "length", "position",
        "outs", "ab"}} for all active injuries on a team. length is the whole
        injury in days (days is what's left of it). outs and ab are the player's regular-season
        pitching outs and at-bats in the league's current season (0 if none)."""
        if not team_id:
            return {}
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT pi.player_id,
                      (pi.return_date::date - %s::date) AS days_remaining,
                      pi.injury_type,
                      pi.games_remaining AS length,
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
                "injury_type": r["injury_type"],
                "length": r["length"],
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

    def get_team_injury_types(self, team_id: str, as_of=None) -> dict[str, str]:
        """Return {player_id: injury_type} for the injured players on a team
        whose injury has a type (older injuries have none)."""
        if not team_id:
            return {}
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT pi.player_id, pi.injury_type
                FROM player_injuries pi
                JOIN team_players tp ON tp.player_id = pi.player_id
                WHERE tp.team_id = %s
                AND pi.return_date::date > %s::date
                AND pi.league_id = %s
                AND pi.injury_type IS NOT NULL""",
            (team_id, as_of, self.league_id),
        ).fetchall()
        return {r["player_id"]: r["injury_type"] for r in rows}

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

    def get_last_injury(self, player_id: str) -> dict | None:
        """The player's most recent injury log row."""
        row = self.conn.execute(
            """SELECT * FROM player_injury_log WHERE player_id = %s
               ORDER BY injury_date DESC, id DESC LIMIT 1""",
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_injuries_by_year(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT pil.injury_date, pil.severity, pil.injury_type,
                   pil.games_missed, pil.activity, pil.outcome, pil.effects,
                   pil.cap_drop, s.year as season_year
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
                   pil.injury_date, pil.severity, pil.injury_type, pil.activity,
                   pil.games_missed AS days_missed, pil.outcome, pil.effects
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
        injury_type=None,
    ):
        """
        Record an injury suffered on game_date. The player misses `days`
        calendar days (rolled from the severity tier if not given) and is
        available again the day after that. `team_id` is the team the
        player was hurt playing for. `injury_type` is the specific injury
        (src/player/injury_types.py); its own day range is used when rolling.
        """
        injury_day = _to_date(game_date)
        days_missed = (
            days
            if days is not None
            else roll_days_missed(severity, rng, injury_type=injury_type)
        )
        return_date = injury_day + timedelta(days=days_missed + 1)

        existing = self.get(player_id, as_of=injury_day + timedelta(days=1))
        if existing and existing.return_date >= return_date:
            logger.debug("Player %s already has a worse injury, skipping.", player_id)
            return existing

        rust = self._roll_rust(player_id, injury_type, days_missed, rng)

        injury = PlayerInjury(
            player_id=player_id,
            return_date=return_date,
            days_remaining=days_missed,
            injury_type=injury_type,
        )

        # An earlier injury he's back from gets its lasting outcome before
        # this one takes its place.
        self.resolve_returns(as_of=injury_day, player_ids=[player_id], rng=rng)

        cursor = self.conn.cursor()
        with self.conn.transaction():
            cursor.execute(
                """
                INSERT INTO player_injury_log
                    (player_id, season_id, team_id, games_missed, severity,
                     injury_date, activity, injury_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    player_id,
                    season_id,
                    team_id,
                    days_missed,
                    severity,
                    injury_day.isoformat(),
                    activity,
                    injury_type,
                ),
            )
            log_id = cursor.fetchone()["id"]
            # games_remaining is legacy (pre day-based injuries); it now just
            # records the length of the current injury in days.
            cursor.execute(
                """
                INSERT INTO player_injuries
                    (player_id, league_id, games_remaining, return_date,
                     injury_type, rust, rust_days, log_id, lasting_done)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                ON CONFLICT(player_id, league_id) DO UPDATE SET
                    games_remaining = excluded.games_remaining,
                    return_date = excluded.return_date,
                    injury_type = excluded.injury_type,
                    rust = excluded.rust,
                    rust_days = excluded.rust_days,
                    log_id = excluded.log_id,
                    lasting_done = FALSE
                """,
                (
                    player_id,
                    self.league_id,
                    days_missed,
                    return_date.isoformat(),
                    injury_type,
                    Jsonb(rust[0]) if rust else None,
                    rust[1] if rust else None,
                    log_id,
                ),
            )

        logger.info(
            "Player %s injured: %s %s (%d days, back %s).",
            player_id,
            severity,
            injury_type or "",
            days_missed,
            return_date.isoformat(),
        )
        return injury

    def _roll_rust(self, player_id, injury_type, days_missed, rng):
        """Roll the rust this injury will leave, from the player's age and,
        for hitters only, durability."""
        if not injury_type:
            return None
        row = self.conn.execute(
            """SELECT p.position, ps.age, ps.durability
               FROM players p LEFT JOIN player_skills ps ON ps.player_id = p.id
               WHERE p.id = %s""",
            (player_id,),
        ).fetchone()
        age = row["age"] if row else None
        durability = None
        if row and not is_pitcher(row["position"] or ""):
            durability = row["durability"]
        return roll_rust(injury_type, days_missed, age, durability, rng)

    # ------------------------------------------------------------------
    # Rust
    # ------------------------------------------------------------------

    def get_rust(self, player_ids, as_of=None) -> dict[str, dict]:
        """Rust still on these players on `as_of`: {player_id: {"skills":
        {skill: points down now}, "days_left": days until it's gone if he
        plays every day, "injury_type"}}. Only players back from their
        injury with some rust left are listed.

        Rust fades a little every day after the return date, twice as fast
        on days the player doesn't appear in a game."""
        if not player_ids:
            return {}
        as_of = self._as_of(as_of)
        rows = self.conn.execute(
            """SELECT pi.player_id, pi.rust, pi.rust_days, pi.injury_type,
                      (%s::date - pi.return_date::date) AS days_back,
                      (SELECT COUNT(DISTINCT g.game_date)
                       FROM player_game_stats s JOIN games g ON g.id = s.game_id
                       WHERE s.player_id = pi.player_id
                         AND g.game_date::date >= pi.return_date::date
                         AND g.game_date::date < %s::date) AS days_played
               FROM player_injuries pi
               WHERE pi.league_id = %s AND pi.player_id = ANY(%s)
                 AND pi.rust IS NOT NULL
                 AND pi.return_date::date <= %s::date
                 AND pi.return_date::date + CEIL(pi.rust_days)::int > %s::date""",
            (as_of, as_of, self.league_id, list(player_ids), as_of, as_of),
        ).fetchall()
        out = {}
        for r in rows:
            skills = {k: float(v) for k, v in (r["rust"] or {}).items()}
            args = (skills, float(r["rust_days"]), r["days_back"], r["days_played"])
            left = rust_left(*args)
            if left:
                out[r["player_id"]] = {
                    "skills": left,
                    "days_left": rust_days_to_clear(*args),
                    "injury_type": r["injury_type"],
                }
        return out

    # ------------------------------------------------------------------
    # Lasting effects
    # ------------------------------------------------------------------

    def resolve_returns(self, as_of=None, player_ids=None, rng=None) -> list[dict]:
        """Roll the lasting outcome of every injury that's over by `as_of`
        and hasn't had one yet (src/player/injury_types.py LASTING), and
        write it into the player's skills: a lasting loss, sometimes a
        lower talent cap too, or for a lucky few a gain (which raises the
        cap with it). Limit to some players with `player_ids`.

        Returns one dict per injury resolved: player_id, log_id,
        injury_type, outcome, effects ({skill: points actually moved}),
        cap_drop."""
        as_of = self._as_of(as_of)
        if player_ids is not None and not player_ids:
            return []
        rows = self.conn.execute(
            """SELECT pi.player_id, pi.injury_type, pi.log_id,
                      p.position, ps.age, ps.durability
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               LEFT JOIN player_skills ps ON ps.player_id = pi.player_id
               WHERE pi.league_id = %s AND NOT pi.lasting_done
                 AND pi.return_date::date <= %s::date
                 AND (%s::text[] IS NULL OR pi.player_id = ANY(%s::text[]))
               ORDER BY pi.player_id
               FOR UPDATE OF pi""",
            (
                self.league_id,
                as_of,
                list(player_ids) if player_ids is not None else None,
                list(player_ids) if player_ids is not None else None,
            ),
        ).fetchall()
        if not rows:
            return []
        season_id = self._current_season_id()
        out = []
        for r in rows:
            pid = r["player_id"]
            pitcher = is_pitcher(r["position"] or "")
            result = None
            if r["age"] is not None:
                result = roll_lasting(
                    r["injury_type"], pitcher, r["age"], r["durability"], rng
                )
            effects = {}
            if result and result.effects:
                effects = self._apply_lasting(pid, result.effects, result.cap_drop)
            self.conn.execute(
                """UPDATE player_injuries SET lasting_done = TRUE
                   WHERE player_id = %s AND league_id = %s""",
                (pid, self.league_id),
            )
            if r["log_id"] is not None and result:
                self.conn.execute(
                    """UPDATE player_injury_log
                       SET outcome = %s, effects = %s, cap_drop = %s,
                           resolved_on = %s, resolved_season_id = %s
                       WHERE id = %s""",
                    (
                        result.outcome,
                        Jsonb(effects),
                        result.cap_drop and any(v < 0 for v in effects.values()),
                        as_of,
                        season_id,
                        r["log_id"],
                    ),
                )
            if result:
                logger.info(
                    "Player %s back from %s: %s %s",
                    pid, r["injury_type"], result.outcome, effects,
                )  # fmt: skip
                out.append(
                    {
                        "player_id": pid,
                        "log_id": r["log_id"],
                        "injury_type": r["injury_type"],
                        "outcome": result.outcome,
                        "effects": effects,
                        "cap_drop": result.cap_drop,
                    }
                )
        return out

    def _apply_lasting(self, player_id, effects, cap_drop) -> dict[str, int]:
        """Move the player's skills by `effects` (kept within 1-100) and
        return how far each actually moved. Gains raise the talent cap by
        the same amount; losses lower it only when `cap_drop`."""
        skills = self.conn.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (player_id,)
        ).fetchone()
        if not skills:
            return {}
        caps = self.conn.execute(
            "SELECT * FROM player_talent_caps WHERE player_id = %s", (player_id,)
        ).fetchone()
        moved: dict[str, int] = {}
        cap_moves: dict[str, int] = {}
        for skill, delta in effects.items():
            if skill not in skills:
                continue
            old = skills[skill]
            new = min(100, max(1, old + delta))
            if new == old:
                continue
            moved[skill] = new - old
            if caps and skill in caps and (new > old or cap_drop):
                cap_moves[skill] = min(100, max(1, caps[skill] + (new - old)))
        if moved:
            sets = ", ".join(f"{k} = %s" for k in moved)
            self.conn.execute(
                f"UPDATE player_skills SET {sets} WHERE player_id = %s",
                [skills[k] + v for k, v in moved.items()] + [player_id],
            )
        if cap_moves:
            sets = ", ".join(f"{k} = %s" for k in cap_moves)
            self.conn.execute(
                f"UPDATE player_talent_caps SET {sets} WHERE player_id = %s",
                list(cap_moves.values()) + [player_id],
            )
        return moved

    def _current_season_id(self) -> str | None:
        """The league's season now (its newest)."""
        row = self.conn.execute(
            """SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (self.league_id,),
        ).fetchone()
        return row["id"] if row else None

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
