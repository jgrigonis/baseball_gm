# src/db/migration_files/migration_101_gm_summary_seen.py
"""
Once a GM has opened the season summary in the offseason, the top bar's
next-move button stays on the next step (Expiring Deals on the Free Agents
tab, then Begin Offseason) instead of sending them back to the summary from
every other page (Josh, 2026-11-09). gms.summary_seen_season_id is the
season whose summary they last opened.
"""

VERSION = 101


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS summary_seen_season_id TEXT")
