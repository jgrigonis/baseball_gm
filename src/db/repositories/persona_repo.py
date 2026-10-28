# src/db/repositories/persona_repo.py
#
# The GM persona library (gm_personas). A persona is created once and never
# edited; only its chance can change, and it can be deleted only while no
# league uses it.

import uuid

from psycopg.types.json import Jsonb


class PersonaRepository:
    def __init__(self, conn):
        self.conn = conn

    def create(
        self, name: str, bio: str, archetype: str, dials: dict, chance: int
    ) -> str:
        persona_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO gm_personas (id, name, bio, archetype, dials, chance)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (persona_id, name, bio, archetype, Jsonb(dials), chance),
        )
        return persona_id

    def get(self, persona_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM gm_personas WHERE id = %s", (persona_id,)
        ).fetchone()
        return dict(row) if row else None

    def name_taken(self, name: str) -> bool:
        return bool(
            self.conn.execute(
                "SELECT 1 FROM gm_personas WHERE lower(name) = lower(%s)", (name,)
            ).fetchone()
        )

    def all(self) -> list[dict]:
        """Every persona, with how many leagues it's in."""
        rows = self.conn.execute(
            """SELECT p.*, COUNT(DISTINCT g.league_id) AS leagues
               FROM gm_personas p
               LEFT JOIN gms g ON g.persona_id = p.id
               GROUP BY p.id
               ORDER BY p.archetype, p.name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def pool(self) -> list[dict]:
        """What a pick draws from: id, chance and dials of every persona."""
        rows = self.conn.execute(
            "SELECT id, name, chance, dials FROM gm_personas ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def in_league(self, league_id: str) -> set[str]:
        rows = self.conn.execute(
            """SELECT DISTINCT persona_id FROM gms
               WHERE league_id = %s AND persona_id IS NOT NULL""",
            (league_id,),
        ).fetchall()
        return {r["persona_id"] for r in rows}

    def leagues_using(self, persona_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT league_id) AS n FROM gms WHERE persona_id = %s",
            (persona_id,),
        ).fetchone()
        return row["n"]

    def set_chance(self, persona_id: str, chance: int) -> None:
        self.conn.execute(
            "UPDATE gm_personas SET chance = %s, updated_at = NOW() WHERE id = %s",
            (chance, persona_id),
        )

    def delete(self, persona_id: str) -> bool:
        """Delete a persona no league uses. False if one does."""
        if self.leagues_using(persona_id):
            return False
        self.conn.execute("DELETE FROM gm_personas WHERE id = %s", (persona_id,))
        return True

    def by_team(self, league_id: str) -> dict[str, dict]:
        """The persona of each AI-run team in a league, by team id: its id,
        name and archetype."""
        rows = self.conn.execute(
            """SELECT g.team_id, p.id, p.name, p.archetype FROM gms g
               JOIN gm_personas p ON p.id = g.persona_id
               WHERE g.league_id = %s AND g.is_ai AND g.team_id IS NOT NULL""",
            (league_id,),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def ai_dials(self, league_id: str) -> dict[str, dict]:
        """The persona dials of each AI-run team in a league, by team id.
        Teams a person runs are left out."""
        rows = self.conn.execute(
            """SELECT g.team_id, p.dials FROM gms g
               JOIN gm_personas p ON p.id = g.persona_id
               WHERE g.league_id = %s AND g.is_ai AND g.team_id IS NOT NULL
                 AND g.fired_at IS NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM gms h
                     WHERE h.league_id = g.league_id AND h.team_id = g.team_id
                       AND NOT h.is_ai AND h.fired_at IS NULL)""",
            (league_id,),
        ).fetchall()
        return {r["team_id"]: r["dials"] for r in rows}
