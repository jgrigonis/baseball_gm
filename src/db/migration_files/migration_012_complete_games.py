# src/db/migration_files/migration_012_complete_games.py
"""
Complete games, shutouts and no-hitters.

The CG and SHO columns existed but were never filled in. Games now credit
them, plus a new no-hitter column, to a starter who was his team's only
pitcher in the game. A no-hitter also needs at least nine innings.

Games already played are backfilled the same way from player_game_stats,
and the season rollups are recounted from them.
"""

VERSION = 12


def upgrade(conn):
    conn.execute(
        """ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS
           pitch_no_hitter INTEGER DEFAULT 0 CHECK (pitch_no_hitter IN (0, 1))"""
    )
    conn.execute(
        """ALTER TABLE player_season_stats ADD COLUMN IF NOT EXISTS
           pitch_no_hitters INTEGER NOT NULL DEFAULT 0"""
    )

    conn.execute(
        """UPDATE player_game_stats pgs SET
               pitch_complete_game = 1,
               pitch_shutout   = CASE WHEN pgs.pitch_runs = 0 THEN 1 ELSE 0 END,
               pitch_no_hitter = CASE WHEN pgs.pitch_hits = 0 AND pgs.pitch_outs >= 27
                                      THEN 1 ELSE 0 END
           WHERE pgs.pitch_game_started = 1
             AND NOT EXISTS (
                 SELECT 1 FROM player_game_stats o
                 WHERE o.game_id = pgs.game_id AND o.team_id = pgs.team_id
                   AND o.player_id <> pgs.player_id AND o.pitch_game_played = 1
             )"""
    )

    conn.execute(
        """UPDATE player_season_stats pss SET
               pitch_complete_games = t.cg,
               pitch_shutouts       = t.sho,
               pitch_no_hitters     = t.nh
           FROM (
               SELECT pgs.player_id, g.season_id, pgs.team_id,
                      g.series_id IS NOT NULL AS is_postseason,
                      SUM(pgs.pitch_complete_game) AS cg,
                      SUM(pgs.pitch_shutout) AS sho,
                      SUM(pgs.pitch_no_hitter) AS nh
               FROM player_game_stats pgs
               JOIN games g ON g.id = pgs.game_id
               WHERE pgs.pitch_complete_game = 1
               GROUP BY pgs.player_id, g.season_id, pgs.team_id,
                        g.series_id IS NOT NULL
           ) t
           WHERE pss.player_id = t.player_id AND pss.season_id = t.season_id
             AND pss.team_id = t.team_id AND pss.is_postseason = t.is_postseason"""
    )
