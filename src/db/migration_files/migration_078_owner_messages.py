"""
The owner's office (src/api/services/owner_office.py): each owner's messages
to their GM, stored once under a key, and the owner's mood each season.
"""

VERSION = 78


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_messages (
            id         BIGSERIAL PRIMARY KEY,
            league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            gm_id      TEXT REFERENCES gms(id) ON DELETE CASCADE,
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            key        TEXT NOT NULL,
            kind       TEXT NOT NULL,
            body       TEXT NOT NULL,
            mood       TEXT,
            created_on TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            seen_at    TIMESTAMPTZ,
            UNIQUE (league_id, team_id, key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_moods (
            league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id   TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            mood      REAL NOT NULL,
            as_of     TEXT,
            PRIMARY KEY (league_id, team_id, season_id)
        )
        """
    )
    for sql in (
        "CREATE INDEX IF NOT EXISTS idx_owner_messages_team ON owner_messages(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_owner_messages_gm ON owner_messages(gm_id)",
        "CREATE INDEX IF NOT EXISTS idx_owner_messages_season ON owner_messages(season_id)",
        "CREATE INDEX IF NOT EXISTS idx_owner_moods_team ON owner_moods(team_id)",
        "CREATE INDEX IF NOT EXISTS idx_owner_moods_season ON owner_moods(season_id)",
    ):
        conn.execute(sql)
