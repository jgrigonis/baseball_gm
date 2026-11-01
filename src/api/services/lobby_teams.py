# src/api/services/lobby_teams.py
#
# Teams in the lobby. Team rows are only made when a league starts, but the
# teams themselves (src/league/world_league.py) are known from the start. So each GM
# waiting in the lobby, person or AI, is dealt one of them by name when they
# join or are picked, and the lobby shows it. A person who joins takes the
# team of the AI GM whose place they take. At the start, each GM gets the
# team of that name.
#
# A league plays with num_teams of them: all 30 World League teams, those
# plus a pick of EXTRA_TEAMS for 32, or a random pick of them for fewer. Each
# pick is the same for the league every time (it's seeded by the league's id).

from __future__ import annotations

import random

from src.league.world_league import EXTRA_TEAMS, WORLD_TEAMS


def world_teams() -> tuple[tuple[str, str], ...]:
    """Every World League team, as (city, mascot)."""
    return tuple((t["city"], t["mascot"]) for t in WORLD_TEAMS)


def team_entries(league_id: str, num_teams: int) -> list[dict]:
    """The teams ({city, mascot}) this league plays with."""
    world = list(WORLD_TEAMS)
    if num_teams >= len(world):
        extra = random.Random(f"extra-teams-{league_id}").sample(
            EXTRA_TEAMS, min(num_teams - len(world), len(EXTRA_TEAMS))
        )
        return world + sorted(extra, key=lambda t: t["city"])
    picked = random.Random(f"teams-{league_id}").sample(world, num_teams)
    return sorted(picked, key=lambda t: t["city"])


def league_teams(conn, league_id: str) -> tuple[tuple[str, str], ...]:
    """The teams this league plays with, as (city, mascot)."""
    row = conn.execute(
        "SELECT num_teams FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not row:
        return ()
    return tuple(
        (t["city"], t["mascot"]) for t in team_entries(league_id, row["num_teams"])
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
    """Every team in the lobby, by city, with who holds it: for a person
    picking theirs. holder is the GM's name, is_ai whether it's an AI GM."""
    rows = conn.execute(
        """SELECT id, display_name, is_ai, lobby_city, lobby_mascot FROM gms
           WHERE league_id = %s AND team_id IS NULL AND lobby_city IS NOT NULL""",
        (league_id,),
    ).fetchall()
    held = {(r["lobby_city"], r["lobby_mascot"]): r for r in rows}
    out = []
    for city, mascot in sorted(league_teams(conn, league_id)):
        gm = held.get((city, mascot))
        out.append(
            {
                "city": city,
                "mascot": mascot,
                "holder_id": gm["id"] if gm else None,
                "holder": gm["display_name"] if gm else None,
                "is_ai": bool(gm and gm["is_ai"]),
            }
        )
    return out


def pick(conn, league_id: str, gm_id: str, city: str, mascot: str) -> bool:
    """A person in the lobby takes this team. If an AI GM holds it, the two
    swap; a team another person holds can't be taken. False if the pick
    isn't allowed."""
    if (city, mascot) not in league_teams(conn, league_id):
        return False
    league = conn.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["state"] != "lobby":
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
