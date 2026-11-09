"""
Rust news (Josh, 2026-11-09): a GM whose Strategy tab rests rusty players
hears when a player's rust wears off, and a sim run until an injury stops
there. Stored as gm_notifications kind 'rust'.
"""

VERSION = 98


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster', 'trade', 'rust'))"""
    )
