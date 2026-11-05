"""
Team owners (src/league/owners.py, plans/owners.md): the site-wide owner
library, seeded with the starting owners, and each team's owner in a league.
Teams get their owner the first time it's needed (src/api/services/owners.py),
so leagues already running pick one up on their own.
"""

import uuid

from psycopg.types.json import Jsonb

VERSION = 75


def upgrade(conn):
    from src.league import owners

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_personas (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            bio        TEXT NOT NULL DEFAULT '',
            archetype  TEXT NOT NULL DEFAULT '',
            weights    JSONB NOT NULL,
            traits     JSONB NOT NULL,
            chance     INTEGER NOT NULL DEFAULT 50 CHECK (chance BETWEEN 0 AND 100),
            created_at TEXT NOT NULL DEFAULT (NOW()),
            updated_at TEXT NOT NULL DEFAULT (NOW())
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_owners (
            league_id     TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id       TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            owner_id      TEXT NOT NULL REFERENCES owner_personas(id),
            rival_team_id TEXT REFERENCES teams(id) ON DELETE SET NULL,
            since_year    INTEGER NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (NOW()),
            PRIMARY KEY (league_id, team_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_owners_owner ON team_owners(owner_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_owners_team ON team_owners(team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_owners_rival ON team_owners(rival_team_id)"
    )

    if not conn.execute("SELECT 1 FROM owner_personas LIMIT 1").fetchone():
        for o in owners.seed():
            conn.execute(
                """INSERT INTO owner_personas
                       (id, name, bio, archetype, weights, traits, chance)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    o["name"],
                    o["bio"],
                    o["archetype"],
                    Jsonb(o["weights"]),
                    Jsonb(o["traits"]),
                    o["chance"],
                ),
            )
