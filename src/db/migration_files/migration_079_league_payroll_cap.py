"""
The league sets the payroll cap, the same for every team, and each owner sets
the GM's budget from it by their Spending trait (src/league/budget.py).
team_budgets gets the season's cap in every row. Older rows take the
season's average budget, which was the flat budget the old rules scaled to.
Seasons still to be taxed get their budgets set again under the new rules,
so the tax and the owner both follow them this season.
"""

VERSION = 79


def upgrade(conn):
    conn.execute("ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS cap BIGINT")
    conn.execute(
        """
        UPDATE team_budgets b SET cap = s.cap
        FROM (SELECT league_id, year,
                     (ROUND(AVG(budget) / 100000) * 100000)::BIGINT AS cap
              FROM team_budgets GROUP BY league_id, year) s
        WHERE b.league_id = s.league_id AND b.year = s.year AND b.cap IS NULL
        """
    )
    # The rules as of this migration: leash = cap x 0.003 per point of
    # Spending over 35, rounded to $1M (src/league/budget.py).
    conn.execute(
        """
        UPDATE team_budgets b
        SET budget = b.cap + (ROUND(
                b.cap * 0.003 * (LEAST(100, GREATEST(0, COALESCE(
                    (SELECT (o.traits->>'spending')::INT
                     FROM team_owners t JOIN owner_personas o ON o.id = t.owner_id
                     WHERE t.league_id = b.league_id AND t.team_id = b.team_id),
                    50))) - 35) / 1000000) * 1000000)::BIGINT
        WHERE b.luxury_tax IS NULL AND b.cap IS NOT NULL
        """
    )
