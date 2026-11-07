# src/db/migration_files/migration_089_minor_league_spending.py
"""
Minor leaguers count against total spending (Josh, 2026-11-06): the full
salaries of minor leaguers never on the 40-man count against the owner's
budget, not payroll or the cap (src/league/budget.py). team_budgets gets a
minor_league column for what a season's farm cost, set when it ends.

Owners' farm allowances are worked out live (BudgetRepository.farm_allowances),
so stored budgets don't change.
"""

VERSION = 89


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS minor_league BIGINT"
    )
