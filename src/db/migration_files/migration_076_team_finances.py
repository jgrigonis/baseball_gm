"""
Owners set budgets (src/league/finances.py): each team's season row in
team_budgets also keeps the revenue the budget was set from, fan interest
coming in and going out, the playoff gate, the final payroll and the profit.
Rows from before have none of it; the season-end assessment fills in what it
can.
"""

VERSION = 76


def upgrade(conn):
    for col, kind in (
        ("revenue", "BIGINT"),
        ("playoff_revenue", "BIGINT"),
        ("payroll", "BIGINT"),
        ("profit", "BIGINT"),
        ("fans_before", "INTEGER"),
        ("fans_after", "INTEGER"),
    ):
        conn.execute(f"ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS {col} {kind}")
