"""
The luxury tax is split among the teams that finished the season under the
league's payroll cap (plans/budget.md, Q6). tax_share is each one's cut, and
it counts in profit.
"""

VERSION = 81


def upgrade(conn):
    conn.execute("ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS tax_share BIGINT")
