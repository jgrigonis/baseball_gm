# src/db/migration_files/migration_012_injury_log_team.py
"""
The injury log records which team a player was on when hurt, so a season
summary can list the injuries each team suffered that season even after
players have been traded or released.

Existing entries are backfilled from the game the player was hurt in: the
injury event that game logged, else the player's box score line from that
day. Entries neither can place get the team the player played the most
games for that season, and stay NULL when the player never played.
"""

VERSION = 12


def upgrade(conn):
    conn.execute("ALTER TABLE player_injury_log ADD COLUMN IF NOT EXISTS team_id TEXT")
    conn.execute("""
        UPDATE player_injury_log pil
        SET team_id = COALESCE(
            (SELECT ge.team_id
             FROM game_events ge
             JOIN games g ON g.id = ge.game_id
             WHERE ge.event_type = 'injury'
               AND ge.player_id = pil.player_id
               AND g.season_id = pil.season_id
               AND g.game_date = pil.injury_date
             LIMIT 1),
            (SELECT pgs.team_id
             FROM player_game_stats pgs
             JOIN games g ON g.id = pgs.game_id
             WHERE pgs.player_id = pil.player_id
               AND g.season_id = pil.season_id
               AND g.game_date = pil.injury_date
             LIMIT 1),
            (SELECT pss.team_id
             FROM player_season_stats pss
             WHERE pss.player_id = pil.player_id
               AND pss.season_id = pil.season_id
             ORDER BY pss.bat_games_played + pss.pitch_games_played DESC
             LIMIT 1)
        )
        WHERE pil.team_id IS NULL
        """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_injury_log_season_team"
        " ON player_injury_log(season_id, team_id)"
    )
