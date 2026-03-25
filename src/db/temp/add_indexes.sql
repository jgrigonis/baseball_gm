-- ============================================================
--  PERFORMANCE INDEXES FOR RECORDS / LEADERBOARD QUERIES
--  Run once: sqlite3 leagues/league.db < add_indexes.sql
-- ============================================================

-- games: the records queries filter on completed + series_id constantly,
-- and the games-per-season subquery groups by season_id + home/away team.
CREATE INDEX IF NOT EXISTS idx_games_completed
    ON games(completed);

CREATE INDEX IF NOT EXISTS idx_games_season_completed
    ON games(season_id, completed);

CREATE INDEX IF NOT EXISTS idx_games_season_completed_series
    ON games(season_id, completed, series_id);

CREATE INDEX IF NOT EXISTS idx_games_season_home_completed
    ON games(season_id, home_team_id, completed);

CREATE INDEX IF NOT EXISTS idx_games_season_away_completed
    ON games(season_id, away_team_id, completed);

-- player_game_stats: the main bottleneck. Queries filter on
-- bat_game_played or pitch_game_played, then aggregate by player_id.
-- The existing single-column indexes on game_id and player_id are not
-- enough for the composite access patterns used in leaderboards.
CREATE INDEX IF NOT EXISTS idx_pgs_player_bat
    ON player_game_stats(player_id, bat_game_played);

CREATE INDEX IF NOT EXISTS idx_pgs_player_pitch
    ON player_game_stats(player_id, pitch_game_played);

CREATE INDEX IF NOT EXISTS idx_pgs_game_bat
    ON player_game_stats(game_id, bat_game_played);

CREATE INDEX IF NOT EXISTS idx_pgs_game_pitch
    ON player_game_stats(game_id, pitch_game_played);

-- team_id is used in the primary_team_subquery correlated lookup
CREATE INDEX IF NOT EXISTS idx_pgs_player_team
    ON player_game_stats(player_id, team_id);
