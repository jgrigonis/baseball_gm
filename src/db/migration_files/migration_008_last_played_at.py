# src/db/migration_files/migration_008_last_played_at.py
"""
When a league was last played, in real-world time: set whenever games are
played or the league moves to a new state. Shown on the leagues page.

Existing leagues start from their most recently played game, if any.
"""

VERSION = 8


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS last_played_at TIMESTAMPTZ"
    )
    conn.execute(
        """UPDATE leagues l SET last_played_at = (
               SELECT MAX(g.updated_at)::timestamptz
               FROM league_seasons ls
               JOIN games g ON g.season_id = ls.season_id
               WHERE ls.league_id = l.id AND g.completed = 1
           )
           WHERE l.last_played_at IS NULL"""
    )
