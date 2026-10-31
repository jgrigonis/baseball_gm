# src/db/migration_files/migration_040_gm_roster_saved.py
"""
The getting-started bar (plans/welcome-screen.md): a new league shows each
human GM links to the draft, roster, lineup and strategy on every page until
they save their roster the first time. gms.roster_saved_at is when they did.
GMs in leagues already past their first draft count as having saved.
"""

VERSION = 40


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS roster_saved_at TIMESTAMPTZ")
    conn.execute(
        """UPDATE gms SET roster_saved_at = NOW()
           WHERE roster_saved_at IS NULL AND league_id IN (
               SELECT id FROM leagues WHERE state NOT IN ('lobby', 'draft'))"""
    )
