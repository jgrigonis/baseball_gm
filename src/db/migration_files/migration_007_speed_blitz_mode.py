# src/db/migration_files/migration_007_speed_blitz_mode.py
"""
Speed blitz is a league mode of its own, next to blitz and long form.
"""

VERSION = 7


def upgrade(conn):
    conn.execute("ALTER TABLE leagues DROP CONSTRAINT IF EXISTS leagues_mode_check")
    conn.execute(
        "ALTER TABLE leagues ADD CONSTRAINT leagues_mode_check "
        "CHECK (mode IN ('blitz', 'speed_blitz', 'longform'))"
    )
