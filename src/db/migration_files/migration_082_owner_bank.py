"""
Each owner keeps a bank that carries over between seasons (plans/budget.md,
Q4): it starts at bank_start (rich owners: a miser lower, a spender higher,
src/league/budget.py starting_bank) in the season bank_year, and every
season's profit from then on goes into it. The balance isn't stored; it's
bank_start plus the profits in team_budgets, so it can't drift.
"""

VERSION = 82


def upgrade(conn):
    conn.execute("ALTER TABLE team_owners ADD COLUMN IF NOT EXISTS bank_start BIGINT")
    conn.execute("ALTER TABLE team_owners ADD COLUMN IF NOT EXISTS bank_year INTEGER")
