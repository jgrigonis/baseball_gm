# src/db/migration_files/migration_146_contract_signed_by.py
"""
Who signed each deal (Josh, 2026-11-19: owners react to overpaid signings,
src/league/overpay.py). player_contracts.signed_by_gm is the person GM
running the team when the deal was made (NULL for AI teams and for deals
made before this). The owner's rare complaint about an overpaid player on
the roster only covers deals the current GM signed, so nobody is blamed for
the last GM's contracts.
"""

VERSION = 146


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS signed_by_gm TEXT"
    )
