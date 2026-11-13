# src/db/migration_files/migration_126_lineup_updates.py
"""
Lineup updates (Josh, 2026-11-13): a Strategy tab setting for whether the
coach keeps a person's saved batting orders as they are ('keep', how it
always worked) or rebuilds and saves them before every game ('daily'),
the way the Lineup tab's Rebuild does, changing them only when a change is
clearly better (src/league/injury_lineup.py).

Also the note on migrations 124 and 125: three migrations were all
numbered 123 (injury rate, catcher pickoffs, the record book), so a
database could only ever record one of them. Catcher pickoffs and the
record book are 124 and 125 now; each only adds what's missing, so they
are safe to run on a database that already has them.
"""

VERSION = 126


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles ADD COLUMN IF NOT EXISTS"
        " lineup_updates TEXT NOT NULL DEFAULT 'keep'"
        " CHECK (lineup_updates IN ('keep', 'daily'))"
    )
