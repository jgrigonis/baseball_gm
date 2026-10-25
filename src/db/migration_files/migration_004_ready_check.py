# src/db/migration_files/migration_004_ready_check.py
"""
Ready-check for multiplayer leagues.

Each league counts its sim periods (sim_period) and, under timer pace, when
the current one's Decision Window ends (period_deadline). A GM is ready for
the current period when gms.ready_period equals leagues.sim_period, so moving
to the next period un-readies everyone at once.
"""

VERSION = 4


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "sim_period INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS period_deadline TIMESTAMPTZ"
    )
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "sim_period_days INTEGER NOT NULL DEFAULT 3"
    )
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS ready_period INTEGER")
