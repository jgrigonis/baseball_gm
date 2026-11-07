# src/db/migration_files/migration_091_trade_request_withdraw.py
"""
A player can take back his trade request (Josh, 2026-11-07): player_moods
counts the weekly updates in a row he's been content or better while his
request is open (src/player/happiness.py withdraws_request).
"""

VERSION = 91


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_moods ADD COLUMN IF NOT EXISTS"
        " content_weeks INTEGER NOT NULL DEFAULT 0"
    )
