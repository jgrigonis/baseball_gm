# src/db/migration_files/migration_114_trade_roster_due.py
"""
Roster after a trade (Josh, 2026-11-11): players a GM trades for land in the
organization, not on the 40-man, so the next-move button sends the GM to the
Roster tab to move them up, then goes back to Play Day.
gms.trade_roster_season_id is the season of the trade that brought players
in; opening the Roster tab clears it.
"""

VERSION = 114


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS trade_roster_season_id TEXT")
