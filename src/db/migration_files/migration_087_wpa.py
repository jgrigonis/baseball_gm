# src/db/migration_files/migration_087_wpa.py
"""
Win probability added (WPA) and run value over the base-out state (RE24)
for hitters and pitchers, on player_game_stats and player_season_stats.

The game engine works them out after each plate appearance
(Game._close_segment, src/game/win_expectancy.py); no play-by-play is
saved. Games played before this have none, so those seasons show 0.
"""

VERSION = 87

COLUMNS = ("bat_wpa", "bat_re24", "pitch_wpa", "pitch_re24")


def upgrade(conn):
    for table in ("player_game_stats", "player_season_stats"):
        for col in COLUMNS:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col}"
                " DOUBLE PRECISION NOT NULL DEFAULT 0"
            )
