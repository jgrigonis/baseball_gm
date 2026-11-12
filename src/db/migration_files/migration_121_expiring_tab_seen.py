# src/db/migration_files/migration_121_expiring_tab_seen.py
"""
Expiring Deals reminder in a multiplayer offseason (Josh, 2026-11-12). With
several GMs the next-move button is the ready toggle, so the offseason's
to-dos ride beside it as pills: the season summary, then the Expiring Deals
tab. gms.expiring_seen_season_id is the season whose expiring deals they
last opened the tab for; until then the pill shows.
"""

VERSION = 121


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gms ADD COLUMN IF NOT EXISTS expiring_seen_season_id TEXT"
    )
