# src/db/migration_files/migration_039_gm_welcome.py
"""
The welcome screen (plans/welcome-screen.md): each human GM sees their new
team once when the league starts, before the draft. gms.welcomed_at is when
they saw it. GMs in leagues already past their first draft count as welcomed.
"""

VERSION = 39


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS welcomed_at TIMESTAMPTZ")
    conn.execute(
        """UPDATE gms SET welcomed_at = NOW()
           WHERE welcomed_at IS NULL AND league_id IN (
               SELECT id FROM leagues WHERE state NOT IN ('lobby', 'draft'))"""
    )
