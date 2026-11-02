"""
Trades become a league setting, picked on the new league form, instead of
following the mode: leagues.trades_enabled. Speed Blitz leagues start with
it off (they had no trades) and every other league with it on. Long Form
still waits on its 26-man roster (trade_deadline.trades_enabled_for).
"""

VERSION = 56


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS"
        " trades_enabled BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute("UPDATE leagues SET trades_enabled = FALSE WHERE mode = 'speed_blitz'")
