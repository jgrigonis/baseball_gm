# src/db/migration_files/migration_139_all_star_plans.py
"""
The All-Star captain's lineup card (Josh, 2026-11-16): each side's batting
order with positions ({player_id, batting_order, position} list) and its
pitching order (player ids, the first one starts), for the All-Star Game
and the Rookie Game. NULL: the game builds them itself.
"""

VERSION = 139


def upgrade(conn):
    for table in ("all_star_games", "rookie_games"):
        for col in ("lineup1", "lineup2", "pitch_order1", "pitch_order2"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} JSONB")
