# src/db/migration_files/migration_093_arbitration_deals.py
"""
Arbitration deals (Josh, 2026-11-07): a player whose rookie deal runs out
signs one-season deals at a growing share of his market price until he
reaches the market (src/player/contracts.py ARBITRATION_SHARE).
player_contracts.kind gets 'arbitration'.
"""

VERSION = 93


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_contracts DROP CONSTRAINT IF EXISTS player_contracts_kind_check"
    )
    conn.execute(
        """ALTER TABLE player_contracts ADD CONSTRAINT player_contracts_kind_check
           CHECK (kind IN ('rookie', 'arbitration', 'standard'))"""
    )
