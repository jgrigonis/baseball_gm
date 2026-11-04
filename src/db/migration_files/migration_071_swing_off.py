# src/db/migration_files/migration_071_swing_off.py
"""
An All-Star or Rookie Game still tied after nine innings is settled by a
home run swing-off (src/league/swing_off.py). swingoff keeps it: each
side's hitters and home runs, any sudden-death rounds and the winner. NULL
when the game was won on the field.
"""

VERSION = 71


def upgrade(conn):
    for table in ("all_star_games", "rookie_games"):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS swingoff JSONB")
