# src/db/migration_files/migration_130_starter_leash_85.py
"""
Starter Leash default 85 (Josh, 2026-11-14), not 95: 95 sent starters
deeper than the old standard (88 pitches) and runs rose with it. Settings
from migration 129 move down a step to keep their place around the new
default: 95 (old standard) to 85 and 85 (old quick hook) to 75, which keeps
the third-time-through hook. 105 and 115 stay.
"""

VERSION = 130


def upgrade(conn):
    conn.execute(
        """UPDATE gm_profiles SET starter_usage = CASE starter_usage
               WHEN '95' THEN '85' WHEN '85' THEN '75' END
           WHERE starter_usage IN ('95', '85')"""
    )
    conn.execute("ALTER TABLE gm_profiles ALTER COLUMN starter_usage SET DEFAULT '85'")
