# src/db/migration_files/migration_106_signing_bonus.py
"""
Draft signing bonuses (Josh, 2026-11-09). A drafted player's bonus is paid
once, by the team that drafted him, in his draft season, and counts with the
minor leagues against the owner's budget; his rookie deal then pays the
minimum. player_contracts.signing_bonus holds it on his rookie deal. Deals
signed before this keep 0: their salaries already have the bonus folded in.
"""

VERSION = 106


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS signing_bonus"
        " INTEGER NOT NULL DEFAULT 0"
    )
