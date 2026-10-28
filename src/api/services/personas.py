# src/api/services/personas.py
#
# GM personas in a league (src/league/personas.py): picking one for an AI
# team, when the league starts or when a person leaves, and reading what each
# team's GM leans toward for trades and team state.
#
# A pick is random, weighted by chance, with no repeats in a league unless
# every pickable persona is already in it. The persona's name becomes the
# GM's display name, and its tactics are written to the GM's gm_profiles row,
# which the game engine reads for every team.

from __future__ import annotations

import random

from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.league import personas
from src.league.personas import Leanings

FALLBACK_NAME = "AI Manager"


def pick(conn, league_id: str, rng: random.Random) -> dict | None:
    """A persona for a new AI GM in this league, or None if the library has
    nothing pickable."""
    repo = PersonaRepository(conn)
    return personas.choose(repo.pool(), repo.in_league(league_id), rng)


def assign(conn, gm_id: str, persona: dict | None) -> None:
    """Make an AI GM this persona: its name, and its tactics. With no persona,
    the GM is the plain AI Manager on default tactics."""
    if persona is None:
        conn.execute(
            "UPDATE gms SET persona_id = NULL, display_name = %s WHERE id = %s",
            (FALLBACK_NAME, gm_id),
        )
        return
    conn.execute(
        "UPDATE gms SET persona_id = %s, display_name = %s WHERE id = %s",
        (persona["id"], persona["name"], gm_id),
    )
    GMRepository(conn).save_profile(gm_id, personas.profile(persona["dials"]))


def give_persona(conn, league_id: str, gm_id: str, rng: random.Random) -> None:
    """Pick a persona for an AI GM in this league and assign it."""
    assign(conn, gm_id, pick(conn, league_id, rng))


def leanings(conn, league_id: str) -> dict[str, Leanings]:
    """What each team's GM leans toward, by team id. An AI team's comes from
    its persona; a person's team is neutral but for their stats-vs-scouting
    setting."""
    rows = conn.execute(
        """SELECT g.team_id, g.is_ai, p.dials, gp.stats_vs_scouting
           FROM gms g
           LEFT JOIN gm_personas p ON p.id = g.persona_id
           LEFT JOIN gm_profiles gp ON gp.gm_id = g.id
           WHERE g.league_id = %s AND g.team_id IS NOT NULL AND g.fired_at IS NULL
           ORDER BY g.is_ai""",
        (league_id,),
    ).fetchall()
    out: dict[str, Leanings] = {}
    for r in rows:
        if r["team_id"] in out:
            continue  # a person's row comes first
        if r["is_ai"] and r["dials"]:
            out[r["team_id"]] = Leanings.from_dials(r["dials"])
        else:
            stats = r["stats_vs_scouting"]
            out[r["team_id"]] = Leanings(
                stats_vs_scouting=50 if stats is None else stats
            )
    return out


def leaning_of(conn, league_id: str, team_id: str) -> Leanings:
    return leanings(conn, league_id).get(team_id, Leanings())


def card(conn, persona_id: str) -> dict | None:
    """A persona for its card: name, bio, archetype and the dials."""
    p = PersonaRepository(conn).get(persona_id)
    if not p:
        return None
    return p | {"traits": personas.describe(p["dials"])}
