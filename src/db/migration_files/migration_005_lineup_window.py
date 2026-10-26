# src/db/migration_files/migration_005_lineup_window.py
"""
Lineup Window for multiplayer leagues: under timer pace, how long the first
period after the draft (preseason, when GMs set their first lineup) lasts.
"""

VERSION = 5


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "lineup_window_sec INTEGER NOT NULL DEFAULT 600"
    )
