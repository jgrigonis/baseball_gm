# src/api/services/lobby_teams.py
#
# Teams in the lobby. Team rows are only made when a league starts, but the
# teams themselves come from the team pool (src/league/team_pool.py) and are
# known from the start. So each GM waiting in the lobby, person or AI, is
# dealt one of them by name when they join or are picked, and the lobby shows
# it. A person who joins takes the team of the AI GM whose place they take.
# At the start, each GM gets the team of that name.
#
# A league plays with num_teams of them, kept in league_lobby_teams: a draw
# balanced across the pool's regions, made the first time the lobby needs
# it. A person can pick any team in the pool. One already in the league they
# swap with its AI GM; one that isn't comes in in place of the closest team
# (same region first) that no other person holds, so the league keeps its
# size and its mix of regions.

from __future__ import annotations

import random

from src.league import team_facts, team_pool
from src.league.team_pool import PoolTeam


def pool_teams() -> tuple[tuple[str, str], ...]:
    """Every team in the pool, as (city, mascot)."""
    return tuple(t.key for t in team_pool.TEAM_POOL)


def league_teams(conn, league_id: str) -> tuple[tuple[str, str], ...]:
    """The teams this league plays with, as (city, mascot), by city. Drawn
    and stored the first time it's asked for."""
    rows = _stored(conn, league_id)
    if not rows:
        _seed(conn, league_id)
        rows = _stored(conn, league_id)
    return tuple(sorted(rows))


def _stored(conn, league_id: str) -> list[tuple[str, str]]:
    return [
        (r["city"], r["mascot"])
        for r in conn.execute(
            "SELECT city, mascot FROM league_lobby_teams WHERE league_id = %s",
            (league_id,),
        ).fetchall()
    ]


def _seed(conn, league_id: str) -> None:
    """Draw the league's teams: any its lobby GMs already hold (a league
    from before the draw was stored), then a balanced pick of the rest."""
    league = conn.execute(
        "SELECT num_teams FROM leagues WHERE id = %s FOR UPDATE", (league_id,)
    ).fetchone()
    if not league or _stored(conn, league_id):
        return
    held = conn.execute(
        """SELECT lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s AND team_id IS NULL AND lobby_city IS NOT NULL
           ORDER BY created_at, id""",
        (league_id,),
    ).fetchall()
    keep = [
        t
        for t in (team_pool.get(r["lobby_city"], r["lobby_mascot"]) for r in held)
        if t
    ]
    teams = team_pool.draw(
        league["num_teams"], random.Random(f"teams-{league_id}"), keep=keep
    )
    for t in teams:
        conn.execute(
            """INSERT INTO league_lobby_teams (league_id, city, mascot)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (league_id, t.city, t.mascot),
        )


def deal(conn, league_id: str, rng: random.Random | None = None) -> None:
    """Give each GM in this league's lobby without a team one nobody else
    has, at random, oldest GM first."""
    rng = rng or random.Random()
    league = conn.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["state"] != "lobby":
        return
    rows = conn.execute(
        """SELECT id, lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s AND team_id IS NULL
           ORDER BY created_at, id""",
        (league_id,),
    ).fetchall()
    taken = {(r["lobby_city"], r["lobby_mascot"]) for r in rows if r["lobby_city"]}
    free = [t for t in league_teams(conn, league_id) if t not in taken]
    rng.shuffle(free)
    for r in rows:
        if r["lobby_city"]:
            continue
        if not free:
            break
        city, mascot = free.pop()
        conn.execute(
            "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
            (city, mascot, r["id"]),
        )


def claims(conn, league_id: str, team_ids: list[str]) -> dict[str, str]:
    """At the start: the team each lobby GM was dealt, as gm id -> team id,
    among the league's new teams. A team goes to one GM only."""
    rows = conn.execute(
        """SELECT g.id AS gm_id, t.id AS team_id
           FROM gms g
           JOIN teams t ON t.city = g.lobby_city AND t.mascot = g.lobby_mascot
           WHERE g.league_id = %s AND g.team_id IS NULL AND t.id = ANY(%s)
           ORDER BY g.created_at, g.id""",
        (league_id, list(team_ids)),
    ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        if r["gm_id"] not in out and r["team_id"] not in out.values():
            out[r["gm_id"]] = r["team_id"]
    return out


def choices(conn, league_id: str) -> list[dict]:
    """Every team in the pool, by city, for a person picking theirs: whether
    it's in the league (in_league) and who holds it. holder is the GM's
    name, is_ai whether it's an AI GM. Picking one that isn't in the league
    brings it in."""
    rows = conn.execute(
        """SELECT id, display_name, is_ai, lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s AND team_id IS NULL AND lobby_city IS NOT NULL""",
        (league_id,),
    ).fetchall()
    held = {(r["lobby_city"], r["lobby_mascot"]): r for r in rows}
    in_league = set(league_teams(conn, league_id))
    out = []
    for city, mascot in sorted(set(pool_teams()) | in_league):
        gm = held.get((city, mascot))
        pool = team_pool.get(city, mascot)
        out.append(
            {
                "city": city,
                "mascot": mascot,
                "region": pool.region if pool else None,
                # "Big · Cold": the picker shows it after the name.
                "facts": team_facts.short(city, mascot),
                "in_league": (city, mascot) in in_league,
                "holder_id": gm["id"] if gm else None,
                "holder": gm["display_name"] if gm else None,
                "is_ai": bool(gm and gm["is_ai"]),
            }
        )
    return out


def pick(conn, league_id: str, gm_id: str, city: str, mascot: str) -> bool:
    """A person in the lobby takes this team. If an AI GM holds it, the two
    swap; a team another person holds can't be taken. A pool team that isn't
    in the league comes in, and the closest team no other person holds goes
    out (their own old one, or an AI GM's, who gets the person's old one).
    False if the pick isn't allowed."""
    league = conn.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["state"] != "lobby":
        return False
    teams = league_teams(conn, league_id)
    if (city, mascot) not in teams and team_pool.get(city, mascot) is None:
        return False
    # Lock the lobby so two people can't take the same team at once.
    rows = conn.execute(
        """SELECT id, is_ai, team_id, lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s ORDER BY id FOR UPDATE""",
        (league_id,),
    ).fetchall()
    me = next((r for r in rows if r["id"] == gm_id), None)
    if not me or me["is_ai"] or me["team_id"]:
        return False
    if (city, mascot) not in teams:
        return _bring_in(conn, league_id, me, rows, teams, team_pool.get(city, mascot))
    holder = next(
        (
            r
            for r in rows
            if r["id"] != gm_id
            and not r["team_id"]
            and (r["lobby_city"], r["lobby_mascot"]) == (city, mascot)
        ),
        None,
    )
    if holder and not holder["is_ai"]:
        return False
    if holder:
        conn.execute(
            "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
            (me["lobby_city"], me["lobby_mascot"], holder["id"]),
        )
    conn.execute(
        "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
        (city, mascot, gm_id),
    )
    if holder and not me["lobby_city"]:
        deal(conn, league_id)  # the AI GM gave up its team for none
    return True


def _bring_in(conn, league_id: str, me, rows, teams, new: PoolTeam) -> bool:
    """``me`` takes ``new``, a pool team not yet in the league, in place of
    the closest league team no other person holds."""
    holders = {
        (r["lobby_city"], r["lobby_mascot"]): r
        for r in rows
        if not r["team_id"] and r["lobby_city"]
    }
    mine = (me["lobby_city"], me["lobby_mascot"])
    out_candidates = [
        t
        for t in (team_pool.get(*key) for key in teams)
        if t and (t.key == mine or t.key not in holders or holders[t.key]["is_ai"])
    ]
    out = team_pool.closest(new, out_candidates)
    if out is None:
        return False  # people hold every team
    conn.execute(
        """UPDATE league_lobby_teams SET city = %s, mascot = %s
           WHERE league_id = %s AND city = %s AND mascot = %s""",
        (new.city, new.mascot, league_id, out.city, out.mascot),
    )
    ai = holders.get(out.key)
    if ai and ai["id"] != me["id"]:
        # The AI GM gives up its team and takes the person's old one.
        conn.execute(
            "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
            (me["lobby_city"], me["lobby_mascot"], ai["id"]),
        )
    conn.execute(
        "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
        (new.city, new.mascot, me["id"]),
    )
    if ai and ai["id"] != me["id"] and not me["lobby_city"]:
        deal(conn, league_id)  # the AI GM gave up its team for none
    return True
