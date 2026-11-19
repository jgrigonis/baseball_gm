# src/db/migration_files/migration_143_front_office_undo.py
"""
Close the front office round trip (Josh, 2026-11-18): near the owner's hard
limit a GM could cut every department to Bare bones, sign a free agent with
the freed room, then raise them all back to Standard, which was always
allowed. team_budgets.fo_undo_spend records the team's total spending just
before its front office cuts this season. Raising a department back up to
Standard past the limit is allowed only while spending stays within that,
so an undo is free until the freed money has been spent.
"""

VERSION = 143


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS fo_undo_spend BIGINT"
    )
