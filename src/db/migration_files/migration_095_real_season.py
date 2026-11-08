# src/db/migration_files/migration_095_real_season.py
"""
Real seasons (Josh, 2026-11-08): a league can start with a real MLB
season's players instead of generated ones (src/league/real_seasons/).
leagues.real_season is that season's year, NULL for a generated league.
"""

VERSION = 95


def upgrade(conn):
    conn.execute("ALTER TABLE leagues ADD COLUMN IF NOT EXISTS real_season INTEGER")
