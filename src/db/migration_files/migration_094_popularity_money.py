# src/db/migration_files/migration_094_popularity_money.py
"""
Popularity money (Josh, 2026-11-07): teams whose fans are keen earn extra
revenue (src/league/finances.py popularity_money). team_budgets records
what each finished season earned from it.
"""

VERSION = 94


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS popularity_revenue BIGINT"
    )
