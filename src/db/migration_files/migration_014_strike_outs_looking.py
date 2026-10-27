# src/db/migration_files/migration_014_strike_outs_looking.py
"""
Strikeouts looking, for batters and pitchers.

Games now record whether each strikeout was looking or swinging. Games
played before this have no record of which it was, so they stay at 0.
"""

VERSION = 14


def upgrade(conn):
    for column in ("bat_strike_outs_looking", "pitch_strike_outs_looking"):
        conn.execute(
            f"""ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS
                {column} INTEGER DEFAULT 0 CHECK ({column} >= 0)"""
        )
        conn.execute(
            f"""ALTER TABLE player_season_stats ADD COLUMN IF NOT EXISTS
                {column} INTEGER NOT NULL DEFAULT 0"""
        )
