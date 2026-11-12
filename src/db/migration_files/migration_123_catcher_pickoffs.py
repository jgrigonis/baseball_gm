# src/db/migration_files/migration_123_catcher_pickoffs.py
"""
Catcher pickoffs (Josh, 2026-11-12): the game engine now has catchers
throwing behind runners (src/game/resolvers/catcher_pickoff.py). Each one
the catcher gets is counted on his game, position and season lines.
"""

VERSION = 123


def upgrade(conn):
    for table, col in (
        ("player_game_stats", "catcher_pickoffs"),
        ("player_game_fielding", "catcher_pickoffs"),
        ("player_season_stats", "field_catcher_pickoffs"),
    ):
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col}"
            " INTEGER NOT NULL DEFAULT 0"
        )
