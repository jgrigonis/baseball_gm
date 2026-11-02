"""
Rust after an injury (plans/injury-details.md, phase 2): the player comes
back with a few ratings down for a while. player_injuries keeps the rolled
drop per rating (rust) and how many days it lasts if he plays every day
(rust_days); it fades from return_date on, faster on days he doesn't play.
"""

VERSION = 58


def upgrade(conn):
    conn.execute("ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS rust JSONB")
    conn.execute("ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS rust_days REAL")
