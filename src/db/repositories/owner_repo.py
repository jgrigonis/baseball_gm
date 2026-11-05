# src/db/repositories/owner_repo.py
"""
Team owners (rules in src/league/owners.py).

Uses tables:
- owner_personas  the site-wide owner library. An owner is created once and
                  never edited; only its chance can change, and it can be
                  deleted only while no league uses it.
- team_owners     each team's owner in a league, its rival, and the first
                  season the owner judges
"""

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb


class OwnerRepository:
    def __init__(self, conn):
        self.conn = conn

    # ── The library ──────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        bio: str,
        archetype: str,
        weights: dict,
        traits: dict,
        chance: int,
    ) -> str:
        owner_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO owner_personas
                   (id, name, bio, archetype, weights, traits, chance)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (owner_id, name, bio, archetype, Jsonb(weights), Jsonb(traits), chance),
        )
        return owner_id

    def get(self, owner_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM owner_personas WHERE id = %s", (owner_id,)
        ).fetchone()
        return dict(row) if row else None

    def name_taken(self, name: str) -> bool:
        return bool(
            self.conn.execute(
                "SELECT 1 FROM owner_personas WHERE lower(name) = lower(%s)", (name,)
            ).fetchone()
        )

    def all(self) -> list[dict]:
        """Every owner, with how many leagues they're in."""
        rows = self.conn.execute(
            """SELECT o.*, COUNT(DISTINCT t.league_id) AS leagues
               FROM owner_personas o
               LEFT JOIN team_owners t ON t.owner_id = o.id
               GROUP BY o.id
               ORDER BY o.archetype, o.name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def pool(self) -> list[dict]:
        """What a draw picks from: id, archetype and chance of every owner."""
        rows = self.conn.execute(
            "SELECT id, name, archetype, chance FROM owner_personas ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def leagues_using(self, owner_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT league_id) AS n FROM team_owners WHERE owner_id = %s",
            (owner_id,),
        ).fetchone()
        return row["n"]

    def set_chance(self, owner_id: str, chance: int) -> None:
        self.conn.execute(
            "UPDATE owner_personas SET chance = %s, updated_at = NOW() WHERE id = %s",
            (chance, owner_id),
        )

    def delete(self, owner_id: str) -> bool:
        """Delete an owner no league uses. False if one does."""
        if self.leagues_using(owner_id):
            return False
        self.conn.execute("DELETE FROM owner_personas WHERE id = %s", (owner_id,))
        return True

    # ── Owners in a league ───────────────────────────────────────────────────

    def in_league(self, league_id: str) -> dict[str, dict]:
        """Each team's owner in a league, by team id: the team_owners row
        with the owner's name, bio, archetype, weights and traits."""
        rows = self.conn.execute(
            """SELECT t.team_id, t.owner_id, t.rival_team_id, t.since_year,
                      o.name, o.bio, o.archetype, o.weights, o.traits
               FROM team_owners t
               JOIN owner_personas o ON o.id = t.owner_id
               WHERE t.league_id = %s""",
            (league_id,),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def seat(
        self,
        league_id: str,
        team_id: str,
        owner_id: str,
        rival_team_id: str | None,
        since_year: int,
    ) -> None:
        """Give a team its owner. A team that already has one keeps it."""
        self.conn.execute(
            """INSERT INTO team_owners
                   (league_id, team_id, owner_id, rival_team_id, since_year)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (league_id, team_id) DO NOTHING""",
            (league_id, team_id, owner_id, rival_team_id, since_year),
        )
