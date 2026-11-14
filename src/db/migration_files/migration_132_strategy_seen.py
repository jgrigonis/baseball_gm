# src/db/migration_files/migration_132_strategy_seen.py
"""
A Strategy pill beside Play Opening Day in single player (Josh,
2026-11-14), until the GM opens the Strategy tab that preseason.
gms.strategy_seen_season_id is the season whose preseason they last opened
it in (like roster/lineup, migration 112).
"""

VERSION = 132


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gms ADD COLUMN IF NOT EXISTS strategy_seen_season_id TEXT"
    )
