# src/db/migration_files/migration_028_fielding_double_triple_plays.py
"""
Double plays and triple plays for fielders.

Every fielder with a putout or assist on a double or triple play now gets
credit for it, per game, per position, and per season. Games played before
this didn't record who turned them, so they stay at 0.
"""

VERSION = 28


def upgrade(conn):
    for column in ("field_double_plays", "field_triple_plays"):
        conn.execute(
            f"""ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS
                {column} INTEGER DEFAULT 0 CHECK ({column} >= 0)"""
        )
        conn.execute(
            f"""ALTER TABLE player_season_stats ADD COLUMN IF NOT EXISTS
                {column} INTEGER NOT NULL DEFAULT 0"""
        )
    for column in ("double_plays", "triple_plays"):
        conn.execute(
            f"""ALTER TABLE player_game_fielding ADD COLUMN IF NOT EXISTS
                {column} INTEGER DEFAULT 0 CHECK ({column} >= 0)"""
        )
