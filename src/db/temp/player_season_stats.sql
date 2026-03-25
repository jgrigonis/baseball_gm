-- ============================================================
--  player_season_stats
--
--  One row per (player, season, team, is_postseason).
--
--  is_postseason = 0  →  regular season games only (series_id IS NULL)
--  is_postseason = 1  →  playoff/postseason games only (series_id IS NOT NULL)
--
--  To query regular season: WHERE is_postseason = 0
--  To query full season:    GROUP BY player_id, season_id, team_id (SUM both rows)
--  To query postseason:     WHERE is_postseason = 1
--
--  Rates (AVG, ERA, WHIP, OBP, SLG, OPS) are NOT stored here —
--  compute them from the counts at query time.
--
--  Populated by:  scripts/build_season_stats.py  (run after each season)
--  Rebuilt fully: scripts/build_season_stats.py --rebuild
-- ============================================================

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       TEXT    NOT NULL,
    season_id       TEXT    NOT NULL,
    team_id         TEXT    NOT NULL,
    is_postseason   INTEGER NOT NULL DEFAULT 0 CHECK (is_postseason IN (0, 1)),

    -- ── Batting ──────────────────────────────────────────────
    bat_games_played    INTEGER NOT NULL DEFAULT 0,
    bat_games_started   INTEGER NOT NULL DEFAULT 0,
    bat_ab              INTEGER NOT NULL DEFAULT 0,
    bat_hits            INTEGER NOT NULL DEFAULT 0,
    bat_doubles         INTEGER NOT NULL DEFAULT 0,
    bat_triples         INTEGER NOT NULL DEFAULT 0,
    bat_home_runs       INTEGER NOT NULL DEFAULT 0,
    bat_rbi             INTEGER NOT NULL DEFAULT 0,
    bat_runs            INTEGER NOT NULL DEFAULT 0,
    bat_walks           INTEGER NOT NULL DEFAULT 0,
    bat_strike_outs     INTEGER NOT NULL DEFAULT 0,
    bat_hbp             INTEGER NOT NULL DEFAULT 0,
    bat_sac_flys        INTEGER NOT NULL DEFAULT 0,
    bat_sac_bunts       INTEGER NOT NULL DEFAULT 0,
    bat_gdp             INTEGER NOT NULL DEFAULT 0,
    bat_gtp             INTEGER NOT NULL DEFAULT 0,
    bat_stolen_bases    INTEGER NOT NULL DEFAULT 0,
    bat_caught_stealing INTEGER NOT NULL DEFAULT 0,

    -- ── Pitching ─────────────────────────────────────────────
    pitch_games_played  INTEGER NOT NULL DEFAULT 0,
    pitch_games_started INTEGER NOT NULL DEFAULT 0,
    pitch_complete_games INTEGER NOT NULL DEFAULT 0,
    pitch_shutouts      INTEGER NOT NULL DEFAULT 0,
    pitch_wins          INTEGER NOT NULL DEFAULT 0,
    pitch_losses        INTEGER NOT NULL DEFAULT 0,
    pitch_saves         INTEGER NOT NULL DEFAULT 0,
    pitch_holds         INTEGER NOT NULL DEFAULT 0,
    pitch_outs          INTEGER NOT NULL DEFAULT 0,  -- divide by 3 for IP
    pitch_hits          INTEGER NOT NULL DEFAULT 0,
    pitch_runs          INTEGER NOT NULL DEFAULT 0,
    pitch_earned_runs   INTEGER NOT NULL DEFAULT 0,
    pitch_home_runs     INTEGER NOT NULL DEFAULT 0,
    pitch_walks         INTEGER NOT NULL DEFAULT 0,
    pitch_strike_outs   INTEGER NOT NULL DEFAULT 0,
    pitch_hit_batters   INTEGER NOT NULL DEFAULT 0,
    pitch_doubles       INTEGER NOT NULL DEFAULT 0,
    pitch_triples       INTEGER NOT NULL DEFAULT 0,
    pitch_pickoffs      INTEGER NOT NULL DEFAULT 0,
    pitch_balks         INTEGER NOT NULL DEFAULT 0,
    pitch_wild_pitches  INTEGER NOT NULL DEFAULT 0,
    pitch_count         INTEGER NOT NULL DEFAULT 0,

    -- ── Fielding ─────────────────────────────────────────────
    field_putouts           INTEGER NOT NULL DEFAULT 0,
    field_assists           INTEGER NOT NULL DEFAULT 0,
    field_errors            INTEGER NOT NULL DEFAULT 0,
    field_passed_balls      INTEGER NOT NULL DEFAULT 0,
    field_catcher_cs        INTEGER NOT NULL DEFAULT 0,
    field_catcher_sb        INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (player_id, season_id, team_id, is_postseason),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE
);

-- Indexes to support leaderboard queries against the rollup
CREATE INDEX IF NOT EXISTS idx_pss_season_postseason
    ON player_season_stats(season_id, is_postseason);

CREATE INDEX IF NOT EXISTS idx_pss_player_season
    ON player_season_stats(player_id, season_id);

CREATE INDEX IF NOT EXISTS idx_pss_team_season
    ON player_season_stats(team_id, season_id);


-- ============================================================
--  POPULATION QUERY
--
--  Run this to build / rebuild the rollup from player_game_stats.
--  Replace the DELETE with a filtered DELETE when doing incremental
--  updates (e.g. after a single season completes).
-- ============================================================

-- Full rebuild: wipe and repopulate
DELETE FROM player_season_stats;

INSERT INTO player_season_stats (
    player_id, season_id, team_id, is_postseason,

    bat_games_played, bat_games_started,
    bat_ab, bat_hits, bat_doubles, bat_triples, bat_home_runs,
    bat_rbi, bat_runs, bat_walks, bat_strike_outs, bat_hbp,
    bat_sac_flys, bat_sac_bunts, bat_gdp, bat_gtp,
    bat_stolen_bases, bat_caught_stealing,

    pitch_games_played, pitch_games_started, pitch_complete_games, pitch_shutouts,
    pitch_wins, pitch_losses, pitch_saves, pitch_holds,
    pitch_outs, pitch_hits, pitch_runs, pitch_earned_runs, pitch_home_runs,
    pitch_walks, pitch_strike_outs, pitch_hit_batters,
    pitch_doubles, pitch_triples, pitch_pickoffs, pitch_balks, pitch_wild_pitches,
    pitch_count,

    field_putouts, field_assists, field_errors,
    field_passed_balls, field_catcher_cs, field_catcher_sb
)
SELECT
    pgs.player_id,
    g.season_id,
    pgs.team_id,
    CASE WHEN g.series_id IS NULL THEN 0 ELSE 1 END AS is_postseason,

    -- Batting
    SUM(pgs.bat_game_played),
    SUM(pgs.bat_game_started),
    SUM(pgs.bat_ab),
    SUM(pgs.bat_hits),
    SUM(pgs.bat_doubles),
    SUM(pgs.bat_triples),
    SUM(pgs.bat_home_runs),
    SUM(pgs.bat_rbi),
    SUM(pgs.bat_runs),
    SUM(pgs.bat_walks),
    SUM(pgs.bat_strike_outs),
    SUM(pgs.bat_hbp),
    SUM(pgs.bat_sac_flys),
    SUM(pgs.bat_sac_bunts),
    SUM(pgs.bat_gdp),
    SUM(pgs.bat_gtp),
    SUM(pgs.bat_stolen_bases),
    SUM(pgs.bat_caught_stealing),

    -- Pitching
    SUM(pgs.pitch_game_played),
    SUM(pgs.pitch_game_started),
    SUM(pgs.pitch_complete_game),
    SUM(pgs.pitch_shutout),
    SUM(pgs.pitch_win),
    SUM(pgs.pitch_loss),
    SUM(pgs.pitch_save),
    SUM(pgs.pitch_hold),
    SUM(pgs.pitch_outs),
    SUM(pgs.pitch_hits),
    SUM(pgs.pitch_runs),
    SUM(pgs.pitch_earned_runs),
    SUM(pgs.pitch_home_runs),
    SUM(pgs.pitch_walks),
    SUM(pgs.pitch_strike_outs),
    SUM(pgs.pitch_hit_batters),
    SUM(pgs.pitch_doubles),
    SUM(pgs.pitch_triples),
    SUM(pgs.pitch_pickoffs),
    SUM(pgs.pitch_balks),
    SUM(pgs.pitch_wild_pitches),
    SUM(pgs.pitch_count),

    -- Fielding
    SUM(pgs.field_putouts),
    SUM(pgs.field_assists),
    SUM(pgs.field_errors),
    SUM(pgs.passed_balls),
    SUM(pgs.catcher_cs),
    SUM(pgs.catcher_sb)

FROM player_game_stats pgs
JOIN games g ON pgs.game_id = g.id
GROUP BY pgs.player_id, g.season_id, pgs.team_id,
         CASE WHEN g.series_id IS NULL THEN 0 ELSE 1 END;
