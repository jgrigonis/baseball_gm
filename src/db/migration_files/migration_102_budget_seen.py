# src/db/migration_files/migration_102_budget_seen.py
"""
Set the budget before it locks (Josh, 2026-11-09): the front office and
ticket prices can only change from the draft to Opening Day, and the
next-move button used to go straight to Play Opening Day, so GMs never got
the chance. team_budgets.budget_seen records that the GM opened the Budget
tab between seasons; until then the preseason's next move is "Set Your
Budget".
"""

VERSION = 102


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS budget_seen BOOLEAN"
    )
