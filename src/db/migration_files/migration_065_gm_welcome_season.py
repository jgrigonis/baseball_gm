# src/db/migration_files/migration_065_gm_welcome_season.py
"""
The welcome screen comes back every season as a season preview: before each
draft, a human GM lands on it once. gms.welcomed_season_id is the season
whose preview they last saw. GMs already welcomed count as having seen their
league's first season, so a league waiting on a later draft shows its
preview on the next visit.
"""

VERSION = 65


def upgrade(conn):
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS welcomed_season_id TEXT")
    conn.execute(
        """UPDATE gms g SET welcomed_season_id = (
               SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = g.league_id AND NOT s.is_backstory
               ORDER BY s.year LIMIT 1)
           WHERE g.welcomed_at IS NOT NULL AND g.welcomed_season_id IS NULL"""
    )
