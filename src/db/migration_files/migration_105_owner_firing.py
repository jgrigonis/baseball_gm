# src/db/migration_files/migration_105_owner_firing.py
"""
Owners fire GMs (plans/owners.md, build step 6). leagues.owner_firing is the
league's toggle, set when the league is created (Josh, 2026-11-07); leagues
made before this keep it off, so nobody is fired in a league that never chose
it. gm_firings remembers each firing: who it was (a person or an AI persona),
the team, the owner, the record and what the owner said, since the GM row
itself stays with the team and goes to a new AI GM.
"""

VERSION = 105


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS owner_firing BOOLEAN NOT NULL"
        " DEFAULT FALSE"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gm_firings (
               id           SERIAL PRIMARY KEY,
               league_id    TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               season_id    TEXT REFERENCES seasons(id) ON DELETE SET NULL,
               year         INTEGER NOT NULL,
               team_id      TEXT REFERENCES teams(id) ON DELETE SET NULL,
               gm_id        TEXT REFERENCES gms(id) ON DELETE SET NULL,
               user_id      TEXT REFERENCES users(id) ON DELETE SET NULL,
               persona_id   TEXT,
               display_name TEXT NOT NULL,
               owner_id     TEXT,
               wins         INTEGER NOT NULL DEFAULT 0,
               losses       INTEGER NOT NULL DEFAULT 0,
               message      TEXT,
               fired_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               rehired_team_id TEXT REFERENCES teams(id) ON DELETE SET NULL,
               rehired_at   TIMESTAMPTZ
           )"""
    )
    # Every foreign key gets an index (tests/db/test_init.py).
    for col in (
        "league_id",
        "season_id",
        "team_id",
        "gm_id",
        "user_id",
        "rehired_team_id",
    ):
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_gm_firings_{col} ON gm_firings({col})"
        )
