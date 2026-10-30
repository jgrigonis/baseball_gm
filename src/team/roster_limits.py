# src/team/roster_limits.py
#
# The size of a team's playing roster. In Blitz-style leagues that's the
# 40-man (26man and 40man players), which must hold 25 to 40. A trade can
# leave a roster short; before the team's next game the game promotes the
# best healthy players from the organization, or sends the lowest-rated down
# if it's over. Each move goes in the GM's news.
#
# Players a person's team trades for go on its 40-man (place_arrivals), and
# if that makes more than 40, the lowest-rated go down, arrivals included:
# a star traded for plays, a scrub stays in the organization.
#
# Long Form's 25/26-man rule isn't enforced yet: Long Form doesn't trade.

from __future__ import annotations

import logging

from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.notification_repo import NotificationRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.league.league_modes import is_blitz_style
from src.player.player_value import role_rating

log = logging.getLogger(__name__)

MIN_PLAYING_ROSTER = 25
MAX_PLAYING_ROSTER = 40
PLAYING_STATUSES = ("26man", "40man")


def playing_count(conn, team_id: str) -> int:
    return conn.execute(
        """SELECT COUNT(*) AS n FROM team_players tp
           JOIN player_status ps ON ps.player_id = tp.player_id
           WHERE tp.team_id = %s AND ps.status IN ('26man', '40man')""",
        (team_id,),
    ).fetchone()["n"]


def enforce_roster_limits(
    conn, league_id: str, team_id: str, mode: str | None
) -> list[dict]:
    """Bring the team's playing roster back to 25-40 players. Returns the
    moves made, each {"player_id", "name", "to"}."""
    if not is_blitz_style(mode):
        return []
    count = playing_count(conn, team_id)
    if MIN_PLAYING_ROSTER <= count <= MAX_PLAYING_ROSTER:
        return []

    status_repo = PlayerStatusRepository(conn)
    players = PlayerRepository(conn).get_players_by_team(team_id)
    statuses = {p.id: status_repo.get_status(p.id) for p in players}
    rated = {p.id: role_rating(p) for p in players}
    moves = []

    if count < MIN_PLAYING_ROSTER:
        injured = set(InjuryRepository(conn, league_id).get_team_injuries(team_id))
        pool = [p for p in players if statuses[p.id] == "minors"]
        # Healthy players first, best first.
        pool.sort(key=lambda p: (p.id in injured, -rated[p.id]))
        for p in pool[: MIN_PLAYING_ROSTER - count]:
            status_repo.set_status(p.id, "40man")
            moves.append({"player_id": p.id, "name": p.name, "to": "40man"})
    else:
        on = [p for p in players if statuses[p.id] in PLAYING_STATUSES]
        on.sort(key=lambda p: rated[p.id])
        for p in on[: count - MAX_PLAYING_ROSTER]:
            status_repo.set_status(p.id, "minors")
            moves.append({"player_id": p.id, "name": p.name, "to": "minors"})

    _tell_gm(conn, league_id, team_id, moves)
    log.info("Team %s roster had %s players: moved %s", team_id, count, len(moves))
    return moves


def place_arrivals(
    conn, league_id: str, team_id: str, arrival_ids: list[str], since=None
) -> list[dict]:
    """Put players a team just traded for on its 40-man, sending the
    lowest-rated down if that makes more than 40. Returns the moves the GM
    hears about, each {"player_id", "name", "to"}."""
    if not arrival_ids:
        return []
    status_repo = PlayerStatusRepository(conn)
    for pid in arrival_ids:
        status_repo.set_status(pid, "40man", since=since)

    players = PlayerRepository(conn).get_players_by_team(team_id)
    statuses = {p.id: status_repo.get_status(p.id) for p in players}
    on = [p for p in players if statuses[p.id] in PLAYING_STATUSES]
    on.sort(key=lambda p: role_rating(p))
    down = {p.id for p in on[: max(0, len(on) - MAX_PLAYING_ROSTER)]}
    for pid in down:
        status_repo.set_status(pid, "minors", since=since)

    moves = [
        {"player_id": p.id, "name": p.name, "to": "minors"}
        for p in players
        if p.id in down and p.id not in arrival_ids
    ] + [
        {"player_id": p.id, "name": p.name, "to": "40man"}
        for p in players
        if p.id in arrival_ids and p.id not in down
    ]
    _tell_gm(conn, league_id, team_id, moves)
    return moves


def _tell_gm(conn, league_id: str, team_id: str, moves: list[dict]) -> None:
    gm = GMRepository(conn).get_human_gm_for_team(league_id, team_id)
    if not gm:
        return
    notes = NotificationRepository(conn)
    for m in moves:
        notes.add(gm, "roster", {"name": m["name"], "to": m["to"]})
