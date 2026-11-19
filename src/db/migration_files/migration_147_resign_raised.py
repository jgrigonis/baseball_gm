# src/db/migration_files/migration_147_resign_raised.py
"""
A counter higher than his ask raises his Re-sign price (Josh, 2026-11-19):
resign_talks.resign_salary / resign_years hold what Re-sign pays after
talks, so a GM can't dodge a higher answer by clicking Re-sign. It only
ever goes up within a window (src/api/services/resign_offers.py).
"""

VERSION = 147


def upgrade(conn):
    conn.execute(
        "ALTER TABLE resign_talks ADD COLUMN IF NOT EXISTS resign_salary INTEGER"
    )
    conn.execute(
        "ALTER TABLE resign_talks ADD COLUMN IF NOT EXISTS resign_years INTEGER"
    )
