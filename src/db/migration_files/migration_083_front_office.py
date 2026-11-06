"""
The front office (plans/budget.md, section 7): each team funds Coaching,
Facilities and Analytics at one of five levels (0 Bare bones to 4 Elite,
NULL = Standard) out of its owner's budget, which now covers the front
office too. Seasons not yet taxed get a Standard front office added to
their budgets (src/league/budget.py standard_front_office: 3.75% of the
cap a department, rounded to $100K), so nobody starts squeezed.
"""

VERSION = 83


def upgrade(conn):
    for col in ("coaching", "facilities", "analytics"):
        conn.execute(
            f"ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS {col} SMALLINT"
        )
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS front_office BIGINT"
    )
    conn.execute(
        """
        UPDATE team_budgets
        SET budget = budget + 3 * (ROUND(cap * 0.0375 / 100000) * 100000)::BIGINT
        WHERE luxury_tax IS NULL AND cap IS NOT NULL
        """
    )
