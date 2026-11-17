# src/team/playoff_eligibility.py
#
# Long Form's September 1 rule (Josh, 2026-11-16), as in MLB: a player can
# be on a playoff roster only if he was in the organization's 40-man (or on
# its 60-day injured list) on September 1. A player who came later (a
# September signing or waiver claim, a minor leaguer added late) can still
# play as a replacement for an eligible player who's hurt: a team may carry
# one ineligible player for each eligible one who's injured.
#
# The sim records each team's 40-man the first time it plays on or after
# September 1 (snapshot). A season that never reaches September has no list,
# and then everyone is eligible.

from __future__ import annotations

from datetime import date

from src.db.repositories.injury_repo import InjuryRepository
from src.league.league_modes import is_blitz_style
from src.team.injured_list import InjuredList

CUTOFF = (9, 1)


def _past_cutoff(on: str) -> bool:
    d = date.fromisoformat(str(on)[:10])
    return (d.month, d.day) >= CUTOFF


def snapshot(conn, league_id: str, season_id: str, on: str) -> int:
    """On the first sim day on or after September 1, record every team's
    40-man (26man and 40man players, which includes the 60-day list) in a
    Long Form league. Returns how many players were recorded."""
    if not season_id or not _past_cutoff(on):
        return 0
    league = conn.execute(
        "SELECT mode, state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or is_blitz_style(league["mode"]) or league["state"] != "season":
        return 0
    if conn.execute(
        "SELECT 1 FROM playoff_eligible WHERE season_id = %s LIMIT 1", (season_id,)
    ).fetchone():
        return 0
    cur = conn.execute(
        """INSERT INTO playoff_eligible (league_id, season_id, team_id, player_id)
           SELECT %s, %s, tp.team_id, tp.player_id
           FROM team_players tp
           JOIN league_season_teams lst
             ON lst.team_id = tp.team_id AND lst.league_id = %s AND lst.season_id = %s
           JOIN player_status ps ON ps.player_id = tp.player_id
           WHERE ps.status IN ('26man', '40man')
           ON CONFLICT DO NOTHING""",
        (league_id, season_id, league_id, season_id),
    )
    return cur.rowcount or 0


def eligible(conn, season_id: str | None, team_id: str) -> set[str] | None:
    """The team's playoff-eligible players, or None when the season has no
    list (everyone is eligible)."""
    if not season_id:
        return None
    if not conn.execute(
        "SELECT 1 FROM playoff_eligible WHERE season_id = %s LIMIT 1", (season_id,)
    ).fetchone():
        return None
    rows = conn.execute(
        "SELECT player_id FROM playoff_eligible WHERE season_id = %s AND team_id = %s",
        (season_id, team_id),
    ).fetchall()
    return {r["player_id"] for r in rows}


def replacements_allowed(
    conn, league_id: str, team_id: str, elig: set[str], on: str | None = None
) -> int:
    """How many ineligible players the team may carry: one for each eligible
    player who's hurt or on the injured list."""
    hurt = set(InjuryRepository(conn, league_id).get_team_injuries(team_id, as_of=on))
    hurt |= set(InjuredList(conn, league_id).for_team(team_id))
    return len(hurt & elig)


def problem(
    conn, league_id: str, season_id: str | None, team_id: str, active: list[str]
) -> str | None:
    """Why this playoff active roster breaks the September 1 rule, or None."""
    elig = eligible(conn, season_id, team_id)
    if elig is None:
        return None
    out = [p for p in active if p not in elig]
    allowed = replacements_allowed(conn, league_id, team_id, elig)
    if len(out) <= allowed:
        return None
    rows = conn.execute(
        "SELECT first_name, last_name FROM players WHERE id = ANY(%s)", (out,)
    ).fetchall()
    names = ", ".join(f"{r['first_name']} {r['last_name']}" for r in rows)
    room = (
        f" You can carry {allowed} as a replacement for a hurt eligible player."
        if allowed
        else ""
    )
    return (
        f"Not playoff eligible: {names}. Only players on your 40-man on"
        f" September 1 can be on the playoff roster.{room}"
    )
