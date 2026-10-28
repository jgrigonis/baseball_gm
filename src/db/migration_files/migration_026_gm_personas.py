"""
GM personas (src/league/personas.py): the site-wide library, seeded with
the starting personas, gms.persona_id, and the stats-vs-scouting setting on
gm_profiles. AI GMs already in leagues get a persona, picked the way a new
league picks them, and play by its tactics.
"""

import random
import uuid

from psycopg.types.json import Jsonb

VERSION = 26


def upgrade(conn):
    from src.league import personas

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gm_personas (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL UNIQUE,
            bio        TEXT NOT NULL DEFAULT '',
            archetype  TEXT NOT NULL DEFAULT '',
            dials      JSONB NOT NULL,
            chance     INTEGER NOT NULL DEFAULT 50 CHECK (chance BETWEEN 0 AND 100),
            created_at TEXT NOT NULL DEFAULT (NOW()),
            updated_at TEXT NOT NULL DEFAULT (NOW())
        )
        """
    )
    conn.execute(
        """
        ALTER TABLE gms ADD COLUMN IF NOT EXISTS persona_id TEXT
            REFERENCES gm_personas(id) ON DELETE SET NULL
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gms_persona ON gms(persona_id)")
    conn.execute(
        """
        ALTER TABLE gm_profiles ADD COLUMN IF NOT EXISTS stats_vs_scouting
            INTEGER NOT NULL DEFAULT 50 CHECK (stats_vs_scouting BETWEEN 0 AND 100)
        """
    )

    if not conn.execute("SELECT 1 FROM gm_personas LIMIT 1").fetchone():
        for p in personas.seed():
            conn.execute(
                """INSERT INTO gm_personas (id, name, bio, archetype, dials, chance)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    p["name"],
                    p["bio"],
                    p["archetype"],
                    Jsonb(p["dials"]),
                    p["chance"],
                ),
            )

    pool = [
        dict(r)
        for r in conn.execute(
            "SELECT id, name, chance, dials FROM gm_personas ORDER BY id"
        ).fetchall()
    ]
    gms = conn.execute(
        """SELECT id, league_id FROM gms
           WHERE is_ai AND persona_id IS NULL
           ORDER BY league_id, created_at, id"""
    ).fetchall()
    rng = random.Random(personas.SEED)
    taken: dict[str, set[str]] = {}
    for gm in gms:
        league_taken = taken.setdefault(gm["league_id"], set())
        p = personas.choose(pool, league_taken, rng)
        if not p:
            break
        league_taken.add(p["id"])
        conn.execute(
            "UPDATE gms SET persona_id = %s, display_name = %s WHERE id = %s",
            (p["id"], p["name"], gm["id"]),
        )
        settings = personas.profile(p["dials"])
        conn.execute(
            f"""UPDATE gm_profiles SET {", ".join(f"{k} = %s" for k in settings)}
                WHERE gm_id = %s""",
            [*settings.values(), gm["id"]],
        )
