"""
All-Star voting (plans/all-star-game.md): each team's ballot for a season
(all_star_votes) and the 64 players voted in (all_stars).
"""

VERSION = 33


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_star_votes (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            slot       TEXT NOT NULL,
            pick       INTEGER NOT NULL,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            PRIMARY KEY (season_id, team_id, slot, pick)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_stars (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            slot       TEXT NOT NULL,
            points     INTEGER NOT NULL DEFAULT 0,
            wildcard   BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (season_id, player_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_votes_team ON all_star_votes(team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_votes_player ON all_star_votes(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_stars_player ON all_stars(player_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_all_stars_team ON all_stars(team_id)")
