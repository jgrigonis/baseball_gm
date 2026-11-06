"""
Someone with a private league's join code can watch it, the way anyone can
watch a public league. Entering the code on the Join League page adds a row
here, and get_gm_or_viewer (src/api/dependencies.py) lets them in as a viewer.
"""

VERSION = 80


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_watchers (
            league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (league_id, user_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_league_watchers_user"
        " ON league_watchers(user_id)"
    )
