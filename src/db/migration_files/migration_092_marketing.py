# src/db/migration_files/migration_092_marketing.py
"""
Marketing, a fourth front office department (Josh, 2026-11-07): it moves fan
interest (src/league/budget.py MARKETING_FANS). team_budgets gets a
marketing level (0 Bare bones to 4 Elite, NULL = Standard). Like migration
083, seasons not yet taxed get a Standard department added to their budgets,
so nobody's spending jumps past the owner's number mid-season.
"""

VERSION = 92


def upgrade(conn):
    conn.execute("ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS marketing SMALLINT")
    conn.execute(
        """
        UPDATE team_budgets
        SET budget = budget + (ROUND(cap * 0.0375 / 100000) * 100000)::BIGINT
        WHERE luxury_tax IS NULL AND cap IS NOT NULL
        """
    )
