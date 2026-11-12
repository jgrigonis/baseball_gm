# src/db/migration_files/migration_119_draft_tabs_seen.py
"""
Draft and Free Agents reminders in a multiplayer draft (Josh, 2026-11-12).
With several GMs the next-move button is the ready toggle, so the draft
period's to-dos ride beside it as pills: the Draft tab, then the Free Agents
tab (bids). gms.draft_tab_seen_season_id and gms.fa_tab_seen_season_id are
the season (the league shell's season during the draft) whose draft they
last opened the Draft and Free Agents tabs in; until then the pill shows.
"""

VERSION = 119


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gms ADD COLUMN IF NOT EXISTS draft_tab_seen_season_id TEXT"
    )
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS fa_tab_seen_season_id TEXT")
