VERSION = 1


def upgrade(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_retirements (
            id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            player_id      TEXT NOT NULL,
            league_id      TEXT NOT NULL,
            season_id      TEXT NOT NULL,
            former_team_id TEXT,
            retired_at     TIMESTAMP NOT NULL DEFAULT NOW(),

            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
            FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_player_retirements_league_season
            ON player_retirements(league_id, season_id)
    """)
