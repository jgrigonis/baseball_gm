# src/team/injured_list.py
#
# Long Form's injured list (Josh, 2026-11-14; plans/injury-details.md phase
# 4). A hurt player on the active roster or the 40-man reserve can go on:
#
#   7-day   concussions only
#   10-day  position players
#   15-day  pitchers
#   60-day  anyone; it frees his 40-man spot too
#
# Placement is backdated to when he got hurt, up to 3 days, and he can't come
# off before the list's days are up (eligible_on) or while he's still hurt.
# A player on the list keeps the 40man status (off the active roster, so he
# can't play); the list is its own table. A trade, release or send-down ends
# it: only rows for the player's current team, with him still on the 40-man,
# count. The list clears when the playoffs end.
#
# People place and activate their own players (the Roster tab, with a
# reminder pill); AI teams do it before each game day
# (roster_limits.enforce_active_roster).

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.player.positions import is_pitcher

KINDS = (7, 10, 15, 60)
BACKDATE_DAYS = 3
# An AI team uses the 60-day list for a player out at least this long.
AI_SIXTY_AFTER_DAYS = 45


@dataclass(frozen=True)
class Stint:
    player_id: str
    kind: int
    placed_on: str
    eligible_on: str

    @property
    def sixty(self) -> bool:
        return self.kind == 60


def kinds_for(position: str | None, injury_type: str | None) -> list[int]:
    """The lists this player can go on: the 7-day for a concussion, the
    10-day for a hitter or the 15-day for a pitcher, and the 60-day."""
    out = [15 if is_pitcher((position or "").lower()) else 10]
    if injury_type == "concussion":
        out.insert(0, 7)
    return out + [60]


def ai_kind(position: str | None, injury_type: str | None, days_out: int) -> int:
    """The list an AI team picks: the 60-day for a long injury, otherwise
    the shortest one he can go on."""
    if days_out >= AI_SIXTY_AFTER_DAYS:
        return 60
    return kinds_for(position, injury_type)[0]


def league_today(conn, league_id: str) -> str:
    """The league's next game day (the date on the top bar), which the
    injured list counts from."""
    from src.db.repositories.injury_repo import InjuryRepository
    from src.db.repositories.league_repo import LeagueRepository
    from src.db.repositories.season_repo import SeasonRepository
    from src.web.utils import _current_league_date

    league = LeagueRepository(conn).get_by_id(league_id) or {}
    season_id = SeasonRepository(conn).get_most_recent_season_from_league(league_id)
    on = _current_league_date(
        conn, season_id, league.get("state") or "", all_star_game=False
    )
    return (
        str(on)[:10]
        if on
        else InjuryRepository(conn, league_id).current_date().isoformat()
    )


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


class InjuredList:
    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    # ── Reading ───────────────────────────────────────────────────────────

    def for_team(self, team_id: str) -> dict[str, Stint]:
        """Everyone on the team's injured list now, by player id."""
        rows = self.conn.execute(
            """SELECT il.player_id, il.kind, il.placed_on, il.eligible_on
               FROM injured_list il
               JOIN team_players tp
                 ON tp.player_id = il.player_id AND tp.team_id = il.team_id
               JOIN player_status ps ON ps.player_id = il.player_id
               WHERE il.team_id = %s AND il.league_id = %s
                 AND il.activated_on IS NULL AND ps.status = '40man'""",
            (team_id, self.league_id),
        ).fetchall()
        return {
            r["player_id"]: Stint(
                r["player_id"], r["kind"], _iso(r["placed_on"]), _iso(r["eligible_on"])
            )
            for r in rows
        }

    def sixty_ids(self, team_id: str) -> set[str]:
        return {pid for pid, s in self.for_team(team_id).items() if s.sixty}

    # ── Placing ───────────────────────────────────────────────────────────

    def problem_placing(
        self, team_id: str, player_id: str, kind: int, today: str
    ) -> str | None:
        """Why he can't go on that list, or None if he can."""
        row = self.conn.execute(
            """SELECT p.position, ps.status, pi.injury_type,
                      (pi.return_date::date - %s::date) AS days_out
               FROM team_players tp
               JOIN players p ON p.id = tp.player_id
               JOIN player_status ps ON ps.player_id = tp.player_id
               LEFT JOIN player_injuries pi
                 ON pi.player_id = tp.player_id AND pi.league_id = %s
               WHERE tp.team_id = %s AND tp.player_id = %s""",
            (today, self.league_id, team_id, player_id),
        ).fetchone()
        if not row:
            return "He isn't on your team."
        if row["status"] not in ("26man", "40man"):
            return "Only players on the 40-man go on the injured list."
        if player_id in self.for_team(team_id):
            return "He's already on the injured list."
        if not row["days_out"] or row["days_out"] <= 0:
            return "Only injured players go on the injured list."
        allowed = kinds_for(row["position"], row["injury_type"])
        if kind not in allowed:
            return (
                "He can go on the " + " or ".join(f"{k}-day" for k in allowed) + " IL."
            )
        return None

    def place(self, team_id: str, player_id: str, kind: int, today: str) -> Stint:
        """Put him on the list (check problem_placing first). He comes off
        the active roster; the placement goes back to when he got hurt, up
        to BACKDATE_DAYS."""
        start = date.fromisoformat(today)
        hurt = self.conn.execute(
            """SELECT l.injury_date FROM player_injuries pi
               JOIN player_injury_log l ON l.id = pi.log_id
               WHERE pi.player_id = %s AND pi.league_id = %s""",
            (player_id, self.league_id),
        ).fetchone()
        earliest = start - timedelta(days=BACKDATE_DAYS)
        if hurt and hurt["injury_date"]:
            start = max(
                earliest, min(start, date.fromisoformat(_iso(hurt["injury_date"])))
            )
        else:
            start = max(earliest, start)
        eligible = start + timedelta(days=kind)
        self.conn.execute(
            """INSERT INTO injured_list
                   (league_id, team_id, player_id, kind, placed_on, eligible_on)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (self.league_id, team_id, player_id, kind, start, eligible),
        )
        self.conn.execute(
            "UPDATE player_status SET status = '40man' WHERE player_id = %s",
            (player_id,),
        )
        return Stint(player_id, kind, start.isoformat(), eligible.isoformat())

    # ── Activating ────────────────────────────────────────────────────────

    def ready(self, team_id: str, today: str) -> dict[str, Stint]:
        """Players whose days are up and who are healthy again."""
        stints = self.for_team(team_id)
        if not stints:
            return {}
        hurt = {
            r["player_id"]
            for r in self.conn.execute(
                """SELECT player_id FROM player_injuries
                   WHERE league_id = %s AND player_id = ANY(%s)
                     AND return_date::date > %s::date""",
                (self.league_id, list(stints), today),
            ).fetchall()
        }
        return {
            pid: s
            for pid, s in stints.items()
            if s.eligible_on <= today and pid not in hurt
        }

    def problem_activating(
        self, team_id: str, player_id: str, today: str, forty_room: bool
    ) -> str | None:
        stint = self.for_team(team_id).get(player_id)
        if not stint:
            return "He isn't on your injured list."
        if stint.eligible_on > today:
            return (
                f"He can't come off the {stint.kind}-day IL until {stint.eligible_on}."
            )
        if player_id not in self.ready(team_id, today):
            return "He's still hurt."
        if stint.sixty and not forty_room:
            return "Your 40-man is full. Make room before he comes off the 60-day IL."
        return None

    def activate(self, player_id: str, today: str) -> None:
        """Off the list (check problem_activating first). He stays on the
        40-man; the caller puts him on the active roster if there's room."""
        self.conn.execute(
            """UPDATE injured_list SET activated_on = %s
               WHERE league_id = %s AND player_id = %s AND activated_on IS NULL""",
            (today, self.league_id, player_id),
        )

    def clear_all(self, today: str) -> None:
        """Everyone comes off when the season's over."""
        self.conn.execute(
            """UPDATE injured_list SET activated_on = %s
               WHERE league_id = %s AND activated_on IS NULL""",
            (today, self.league_id),
        )

    # ── Reminders ─────────────────────────────────────────────────────────

    def reminders(self, team_id: str, today: str, min_days: int) -> dict:
        """For a person's team: hurt active players who could go on the list
        (out more than min_days), and players ready to come off it."""
        hurt = self.conn.execute(
            """SELECT tp.player_id FROM team_players tp
               JOIN player_status ps ON ps.player_id = tp.player_id
               JOIN player_injuries pi
                 ON pi.player_id = tp.player_id AND pi.league_id = %s
               WHERE tp.team_id = %s AND ps.status = '26man'
                 AND pi.return_date::date - %s::date > %s""",
            (self.league_id, team_id, today, min_days),
        ).fetchall()
        return {
            "place": [r["player_id"] for r in hurt],
            "activate": list(self.ready(team_id, today)),
        }
