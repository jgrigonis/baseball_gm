# src/db/migration_files/migration_123_injury_rate.py
"""
How often players get hurt in a league, as a percent of the normal rate
(Josh, 2026-11-12). The commissioner picks one of seven steps from 50 to
200 (league_constants.INJURY_RATES); every league so far plays at 100.
"""

VERSION = 123


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS"
        " injury_rate INTEGER NOT NULL DEFAULT 100"
    )
