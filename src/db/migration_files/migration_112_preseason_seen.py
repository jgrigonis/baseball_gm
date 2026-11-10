# src/db/migration_files/migration_112_preseason_seen.py
"""
Roster and Lineup before Opening Day (Josh, 2026-11-10): once the budget is
set, the preseason's next-move button went straight to Play Opening Day, so
GMs played the first game without looking at the roster the draft and free
agency left them or the batting order. gms.roster_seen_season_id and
gms.lineup_seen_season_id are the season whose preseason they last opened
the Roster and Lineup tabs in; until then the next move sends them there.
"""

VERSION = 112


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS roster_seen_season_id TEXT")
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS lineup_seen_season_id TEXT")
