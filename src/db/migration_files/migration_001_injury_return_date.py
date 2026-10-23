# src/db/migration_files/migration_001_injury_return_date.py
"""
Injuries are now tracked in calendar days instead of games.

Adds player_injuries.return_date (the ISO date a player is available again)
and backfills it for existing injuries by treating the remaining games as
remaining days, counted from the day after the league's last completed game.
"""

VERSION = 1


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS return_date TEXT"
    )
    conn.execute("""
        UPDATE player_injuries pi
        SET return_date = to_char(
            COALESCE(
                (SELECT MAX(g.game_date)::date + 1
                 FROM games g
                 JOIN league_seasons ls ON ls.season_id = g.season_id
                 WHERE ls.league_id = pi.league_id AND g.completed = 1),
                CURRENT_DATE
            ) + pi.games_remaining,
            'YYYY-MM-DD'
        )
        WHERE pi.return_date IS NULL AND pi.games_remaining > 0
        """)
