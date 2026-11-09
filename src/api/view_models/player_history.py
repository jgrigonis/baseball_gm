# src/api/view_models/player_history.py
"""
A player's transaction history for the player panel's collapsed History
section: drafted, opening-day roster, debut, trades, signings and re-signs,
releases, waiver claims and retirement, oldest first.

Nothing new is stored: it's pieced together from the tables each move
already writes (draft_picks, trade_offers, player_contracts, waivers,
player_retirements, player_game_stats). Their real-time stamps put the
moves in order, since a league's moves happen one after another. A deal
records the team that signed it, so following the moves in order tells a
re-sign (the team he was already on) from a free agent signing.
"""

from __future__ import annotations

from datetime import datetime, UTC

from src.api.services.hall_of_fame import ordinal
from src.player.contracts import format_salary

# Ties on the same stamp: a deal is signed before it's released.
_ORDER = {
    "draft": 0,
    "opening": 0,
    "sign": 1,
    "debut": 2,
    "trade": 3,
    "release": 4,
    "claim": 5,
    "retire": 6,
}
_END = datetime.max.replace(tzinfo=UTC)


def _ts(v) -> datetime:
    if v is None:
        return _END
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v


def _years(n: int) -> str:
    return f"{n} yr{'s' if n != 1 else ''}"


def player_history(conn, league_id: str, player_id: str) -> list[dict]:
    """The player's moves in this league, oldest first: {year, text}."""
    teams: dict[str, str] = {}

    def team(team_id: str | None) -> str:
        if not team_id:
            return "?"
        if team_id not in teams:
            row = conn.execute(
                "SELECT mascot FROM teams WHERE id = %s", (team_id,)
            ).fetchone()
            teams[team_id] = row["mascot"] if row else "?"
        return f"the {teams[team_id]}"

    events: list[dict] = []

    def add(kind, ts, year, text=None, **extra):
        events.append(
            {"kind": kind, "ts": _ts(ts), "year": year, "text": text, **extra}
        )

    # ── Draft ────────────────────────────────────────────────────────────────
    pick = conn.execute(
        """SELECT dp.round, dp.pick_number, dp.team_id, s.year,
                  dp.picked_at::timestamptz AS ts,
                  dp.pick_number - (SELECT MIN(p2.pick_number) FROM draft_picks p2
                                    WHERE p2.draft_id = dp.draft_id
                                      AND p2.round = dp.round) + 1 AS in_round
           FROM draft_picks dp
           JOIN drafts d ON d.id = dp.draft_id
           JOIN seasons s ON s.id = d.season_id
           WHERE dp.player_id = %s AND d.league_id = %s
           ORDER BY s.year DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    if pick:
        add(
            "draft",
            pick["ts"],
            pick["year"],
            f"Drafted by {team(pick['team_id'])}: {ordinal(pick['round'])} round,"
            f" pick {pick['in_round']} (#{pick['pick_number']} overall)",
            team_id=pick["team_id"],
        )
        # His first big league game.
        debut = conn.execute(
            """SELECT g.game_date, pgs.team_id
               FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id
               JOIN seasons s ON s.id = g.season_id
               WHERE pgs.player_id = %s AND s.year >= %s
               ORDER BY g.game_date LIMIT 1""",
            (player_id, pick["year"]),
        ).fetchone()
        if debut:
            add(
                "debut",
                None,
                int(debut["game_date"][:4]),
                f"Big league debut with {team(debut['team_id'])}"
                f" ({debut['game_date']})",
                game_date=debut["game_date"],
                team_id=debut["team_id"],
            )

    # ── Trades ───────────────────────────────────────────────────────────────
    for r in conn.execute(
        """SELECT o.from_team_id, o.to_team_id, i.from_team_id AS gave, s.year,
                  o.created_on, COALESCE(o.decided_at, o.created_at) AS ts
           FROM trade_offer_items i
           JOIN trade_offers o ON o.id = i.offer_id
           JOIN seasons s ON s.id = o.season_id
           WHERE i.player_id = %s AND o.league_id = %s AND o.status = 'accepted'""",
        (player_id, league_id),
    ).fetchall():
        to = r["to_team_id"] if r["gave"] == r["from_team_id"] else r["from_team_id"]
        add(
            "trade",
            r["ts"],
            r["year"],
            f"Traded from {team(r['gave'])} to {team(to)}",
            team_id=to,
            on=r["created_on"],
        )

    # ── Waivers ──────────────────────────────────────────────────────────────
    waivers = [
        dict(r)
        for r in conn.execute(
            """SELECT from_team_id, claimed_by, status, placed_on,
                      created_at::timestamptz AS ts
               FROM waivers WHERE player_id = %s AND league_id = %s""",
            (player_id, league_id),
        ).fetchall()
    ]
    for w in waivers:
        year = int(w["placed_on"][:4])
        add(
            "release",
            w["ts"],
            year,
            f"Released by {team(w['from_team_id'])}",
            on=w["placed_on"],
        )
        if w["status"] == "claimed" and w["claimed_by"]:
            add(
                "claim",
                w["ts"],
                year,
                f"Claimed off waivers by {team(w['claimed_by'])}",
                team_id=w["claimed_by"],
            )

    # ── Retirement ───────────────────────────────────────────────────────────
    retired = conn.execute(
        """SELECT s.year, r.former_team_id, r.retired_at::timestamptz AS ts
           FROM player_retirements r JOIN seasons s ON s.id = r.season_id
           WHERE r.player_id = %s AND r.league_id = %s
           ORDER BY r.retired_at DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    if retired:
        add("retire", retired["ts"], retired["year"], "Retired", team_id=None)

    # ── Deals ────────────────────────────────────────────────────────────────
    deals = [
        dict(r)
        for r in conn.execute(
            """SELECT team_id, kind, salary, start_year, years, released_year,
                      released_team_id, created_at::timestamptz AS ts
               FROM player_contracts WHERE player_id = %s AND league_id = %s
               ORDER BY created_at::timestamptz, id""",
            (player_id, league_id),
        ).fetchall()
    ]
    opening = None
    if deals and not pick:
        # The league's starting rosters all sign in one go, when it starts.
        opening = conn.execute(
            """SELECT MIN(created_at::timestamptz) AS ts FROM player_contracts
               WHERE league_id = %s""",
            (league_id,),
        ).fetchone()["ts"]
    first_year = None
    if opening is not None:
        row = conn.execute(
            """SELECT MIN(s.year) AS year FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s""",
            (league_id,),
        ).fetchone()
        first_year = row["year"] if row else None
    for i, d in enumerate(deals):
        if d["kind"] == "rookie":
            continue  # his draft deal: the draft says it
        if i == 0 and opening is not None and d["ts"] == opening:
            add(
                "opening",
                d["ts"],
                first_year or d["start_year"],
                f"On the opening-day roster of {team(d['team_id'])}",
                team_id=d["team_id"],
            )
            continue
        add("sign", d["ts"], d["start_year"], deal=d, team_id=d["team_id"])
    # A release off the minors skips waivers, so it has no stamp of its
    # own: it came before his next deal (or his retirement).
    for d in deals:
        rel_team = d["released_team_id"]
        if d["released_year"] is None or not rel_team:
            continue
        if any(w["from_team_id"] == rel_team and w["ts"] >= d["ts"] for w in waivers):
            continue
        later = [
            e["ts"]
            for e in events
            if e["ts"] > d["ts"] and e["kind"] in ("retire", "sign")
        ]
        add(
            "release",
            min(later) if later else None,
            d["released_year"],
            f"Released by {team(rel_team)}",
            before=True,
        )

    # A game has a league date but no stamp: the debut came before the
    # first move made on a later league date, or a deal for a later season.
    for e in events:
        if e["kind"] == "debut":
            later = [
                x["ts"]
                for x in events
                if (x.get("on") and x["on"] > e["game_date"])
                or (x["kind"] in ("sign", "retire") and x["year"] > e["year"])
            ]
            e["ts"] = min(later) if later else _END
            e["before"] = True

    events.sort(
        key=lambda e: (e["ts"], -1 if e.get("before") else 0, _ORDER[e["kind"]])
    )

    # Follow him team to team, so a deal reads as a re-sign or a signing.
    on_team = None
    out = []
    for e in events:
        if e["kind"] == "sign":
            d = e["deal"]
            terms = f"{_years(d['years'])}, {format_salary(d['salary'])}/yr"
            signer = d["team_id"]
            # A waiver claim takes the deal over: it was signed with the
            # team he was on before.
            if (
                on_team
                and signer != on_team
                and any(
                    w["claimed_by"] == signer and w["ts"] > e["ts"] for w in waivers
                )
            ):
                signer = on_team
            if signer and signer == on_team:
                e["text"] = f"Re-signed with {team(signer)}: {terms}"
            else:
                e["text"] = f"Signed with {team(signer)} as a free agent: {terms}"
        if e["kind"] in ("release", "retire"):
            on_team = None
        elif e.get("team_id"):
            on_team = e["team_id"]
        out.append({"year": e["year"], "text": e["text"]})
    return out
