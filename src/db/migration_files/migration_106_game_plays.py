# src/db/migration_files/migration_106_game_plays.py
"""
Play-by-play for the game panel (Josh, 2026-11-09): one JSON row per game,
the list of plays src/game/play_log.py builds. Not for keeping: a new
season's start deletes the league's older rows (offseason_service), so a
league holds at most one season of them, about 6 KB a game before
Postgres compresses it.
"""

VERSION = 106


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS game_plays (
               game_id   TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
               season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
               plays     JSONB NOT NULL
           )"""
    )
    # Every foreign key gets an index (tests/db/test_init.py).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_game_plays_season_id ON game_plays(season_id)"
    )
