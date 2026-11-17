# src/api/view_models/departed.py
"""
Players no longer with a team, for the Stats tab's current season view:
each one gets a short tag ("Traded", "Released", "Retired", "Left") and a
line saying where he went and when ("Traded to Boston, Jul 14").

Nothing new is stored. A player is gone when he's off the team's
team_players rows; the move that took him is his latest trade away from
the team or release by it (trade_offers, waivers, player_contracts), as
in player_history.py.
"""

from __future__ import annotations

from datetime import date, datetime, UTC

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _ts(v) -> datetime:
    if v is None:
        return _EPOCH
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v


def _day(iso: str | None) -> str:
    """'2026-07-14' -> 'Jul 14'."""
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    return f"{d:%b} {d.day}"


def departures(conn, league_id: str, team_id: str, player_ids) -> dict[str, dict]:
    """{player_id: {"tag", "tip"}} for those of `player_ids` no longer on
    the team. Players still with it (majors or minors) aren't in it."""
    ids = list({p for p in player_ids if p})
    if not team_id or not ids:
        return {}
    still = {
        r["player_id"]
        for r in conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s"
            " AND player_id = ANY(%s)",
            (team_id, ids),
        ).fetchall()
    }
    gone = [p for p in ids if p not in still]
    if not gone:
        return {}

    cities: dict[str, str] = {}

    def city(tid: str | None) -> str:
        if not tid:
            return ""
        if tid not in cities:
            row = conn.execute(
                "SELECT city FROM teams WHERE id = %s", (tid,)
            ).fetchone()
            cities[tid] = row["city"] if row else "?"
        return cities[tid]

    # Where each one is now.
    now = {}
    for r in conn.execute(
        "SELECT player_id, team_id FROM team_players WHERE player_id = ANY(%s)",
        (gone,),
    ).fetchall():
        now[r["player_id"]] = r["team_id"]

    # His latest move off this team: a trade or a release onto waivers.
    moves: dict[str, dict] = {}

    def keep(pid, move):
        if pid not in moves or move["ts"] >= moves[pid]["ts"]:
            moves[pid] = move

    for r in conn.execute(
        """SELECT i.player_id, o.from_team_id, o.to_team_id, o.created_on,
                  COALESCE(o.decided_at, o.created_at) AS ts
           FROM trade_offer_items i JOIN trade_offers o ON o.id = i.offer_id
           WHERE i.from_team_id = %s AND i.player_id = ANY(%s)
             AND o.league_id = %s AND o.status = 'accepted'""",
        (team_id, gone, league_id),
    ).fetchall():
        to = r["to_team_id"] if r["from_team_id"] == team_id else r["from_team_id"]
        keep(
            r["player_id"],
            {"kind": "trade", "ts": _ts(r["ts"]), "on": r["created_on"], "to": to},
        )
    for r in conn.execute(
        """SELECT player_id, placed_on, status, claimed_by,
                  created_at::timestamptz AS ts
           FROM waivers
           WHERE from_team_id = %s AND player_id = ANY(%s) AND league_id = %s""",
        (team_id, gone, league_id),
    ).fetchall():
        keep(
            r["player_id"],
            {
                "kind": "release",
                "ts": _ts(r["ts"]),
                "on": r["placed_on"],
                "status": r["status"],
                "to": r["claimed_by"] if r["status"] == "claimed" else None,
            },
        )
    # A release off the minors skips waivers and has no date.
    minors_release = {
        r["player_id"]
        for r in conn.execute(
            """SELECT player_id FROM player_contracts
               WHERE released_team_id = %s AND player_id = ANY(%s)
                 AND league_id = %s AND released_year IS NOT NULL""",
            (team_id, gone, league_id),
        ).fetchall()
    }
    retired = {
        r["player_id"]
        for r in conn.execute(
            """SELECT player_id FROM player_retirements
               WHERE player_id = ANY(%s) AND league_id = %s""",
            (gone, league_id),
        ).fetchall()
    }

    out = {}
    for pid in gone:
        here = now.get(pid)
        move = moves.get(pid)
        if pid in retired and not here:
            out[pid] = {"tag": "Retired", "tip": "Retired"}
            continue
        if move and move["kind"] == "trade":
            tip = f"Traded to {city(move['to'])}"
            if _day(move["on"]):
                tip += f", {_day(move['on'])}"
            out[pid] = {"tag": "Traded", "tip": tip + _since(move["to"], here, city)}
            continue
        if move:
            tip = "Released"
            if _day(move["on"]):
                tip += f" {_day(move['on'])}"
            if move["to"]:
                tip += f", claimed by {city(move['to'])}"
            if move["status"] == "open" and not here:
                tip += ", on waivers"
            else:
                tip += _since(move["to"], here, city)
            out[pid] = {"tag": "Released", "tip": tip}
            continue
        if pid in minors_release:
            out[pid] = {"tag": "Released", "tip": "Released" + _since(None, here, city)}
            continue
        # Nothing on record: he left some other way (a deal ran out).
        out[pid] = {
            "tag": "Left",
            "tip": f"Now with {city(here)}" if here else "Now a free agent",
        }
    return out


def _since(went_to: str | None, here: str | None, city) -> str:
    """Where he's moved on to since, when it isn't where the move took him."""
    if here and here == went_to:
        return ""
    if here:
        return f"; now with {city(here)}" if went_to else f"; signed with {city(here)}"
    return "; now a free agent"


def attach_departures(
    conn, league_id: str, team_id: str | None, *lines: list[dict]
) -> int:
    """Marks each stat line of a player who's left the team with `departed`
    (its tag) and `departed_tip`. Returns how many players have left."""
    rows = [r for group in lines for r in group]
    gone = departures(conn, league_id, team_id, (r["player_id"] for r in rows))
    for r in rows:
        d = gone.get(r["player_id"])
        r["departed"] = d["tag"] if d else None
        r["departed_tip"] = d["tip"] if d else None
    return len(gone)
