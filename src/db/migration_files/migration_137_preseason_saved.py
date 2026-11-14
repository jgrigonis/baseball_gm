# src/db/migration_files/migration_137_preseason_saved.py
"""
Multiplayer preseason pills beside I'm ready (Josh, 2026-11-14): Roster and
Lineup until the GM has saved each that preseason, not just opened it.
gms.roster_saved_season_id and gms.lineup_saved_season_id are the season
whose preseason they last saved each in.
"""

VERSION = 137


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS roster_saved_season_id TEXT")
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS lineup_saved_season_id TEXT")
