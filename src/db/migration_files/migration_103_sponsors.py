"""
Sponsors (Josh, 2026-11-09): one more line of team revenue
(src/league/finances.py). team_budgets.sponsor_deal is the offer the GM
took for the season ('steady' or 'incentive', NULL picked by last season's
record); sponsor_revenue is what it paid, set when the season ends.
"""

VERSION = 103


def upgrade(conn):
    conn.execute("ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS sponsor_deal TEXT")
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS sponsor_revenue BIGINT"
    )
