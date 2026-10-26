# src/db/migration_files/migration_006_num_seasons.py
"""
Number of seasons a league runs, chosen at league creation (1 to 420).
"""

VERSION = 6


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "num_seasons INTEGER NOT NULL DEFAULT 10"
    )
