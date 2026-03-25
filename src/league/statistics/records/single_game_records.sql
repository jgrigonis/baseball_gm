-- ============================================================
--  SINGLE GAME RECORDS
-- ============================================================

-- Helper: total bases = singles + 2*doubles + 3*triples + 4*HR
-- singles = bat_hits - bat_doubles - bat_triples - bat_home_runs

-- BATTING RECORDS
-- ============================================================
-- ============================================================
--  SINGLE GAME RECORDS — 9 INNINGS
-- ============================================================

-- Most At Bats
SELECT '9inn - Most AB' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_ab as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_ab DESC LIMIT 5;

-- Most Hits
SELECT '9inn - Most Hits' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_hits as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_hits DESC LIMIT 5;

-- Most Doubles
SELECT '9inn - Most Doubles' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_doubles as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_doubles DESC LIMIT 5;

-- Most Triples
SELECT '9inn - Most Triples' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_triples as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_triples DESC LIMIT 5;

-- Most Home Runs
SELECT '9inn - Most HR' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_home_runs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_home_runs DESC LIMIT 5;

-- Most Walks
SELECT '9inn - Most Walks' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_walks as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_walks DESC LIMIT 5;

-- Most Stolen Bases
SELECT '9inn - Most SB' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_stolen_bases as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_stolen_bases DESC LIMIT 5;

-- Most RBI
SELECT '9inn - Most RBI' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_rbi as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_rbi DESC LIMIT 5;

-- Most Total Bases
SELECT '9inn - Most Total Bases' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    (pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples - pgs.bat_home_runs)
        + (2 * pgs.bat_doubles)
        + (3 * pgs.bat_triples)
        + (4 * pgs.bat_home_runs) as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY value DESC LIMIT 5;

-- Most Strikeouts (batting)
SELECT '9inn - Most K (batting)' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_strike_outs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played = 9
ORDER BY pgs.bat_strike_outs DESC LIMIT 5;

-- Most Strikeouts (pitching)
SELECT '9inn - Most K (pitching)' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_strike_outs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played = 9
ORDER BY pgs.pitch_strike_outs DESC LIMIT 5;

-- Most Innings Pitched
SELECT '9inn - Most IP' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    (pgs.pitch_outs / 3) || '.' || (pgs.pitch_outs % 3) as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played = 9
ORDER BY pgs.pitch_outs DESC LIMIT 5;

-- Most Walks Allowed
SELECT '9inn - Most BB allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_walks as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played = 9
ORDER BY pgs.pitch_walks DESC LIMIT 5;

-- Most HR Allowed
SELECT '9inn - Most HR allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_home_runs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played = 9
ORDER BY pgs.pitch_home_runs DESC LIMIT 5;

-- Most Hits Allowed
SELECT '9inn - Most H allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_hits as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played = 9
ORDER BY pgs.pitch_hits DESC LIMIT 5;


-- ============================================================
--  SINGLE GAME RECORDS — EXTRA INNINGS (10+)
-- ============================================================

-- Most At Bats
SELECT 'XIP - Most AB' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_ab as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_ab DESC LIMIT 5;

-- Most Hits
SELECT 'XIP - Most Hits' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_hits as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_hits DESC LIMIT 5;

-- Most Doubles
SELECT 'XIP - Most Doubles' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_doubles as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_doubles DESC LIMIT 5;

-- Most Triples
SELECT 'XIP - Most Triples' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_triples as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_triples DESC LIMIT 5;

-- Most Home Runs
SELECT 'XIP - Most HR' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_home_runs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_home_runs DESC LIMIT 5;

-- Most Walks
SELECT 'XIP - Most Walks' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_walks as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_walks DESC LIMIT 5;

-- Most Stolen Bases
SELECT 'XIP - Most SB' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_stolen_bases as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_stolen_bases DESC LIMIT 5;

-- Most RBI
SELECT 'XIP - Most RBI' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_rbi as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_rbi DESC LIMIT 5;

-- Most Total Bases
SELECT 'XIP - Most Total Bases' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    (pgs.bat_hits - pgs.bat_doubles - pgs.bat_triples - pgs.bat_home_runs)
        + (2 * pgs.bat_doubles)
        + (3 * pgs.bat_triples)
        + (4 * pgs.bat_home_runs) as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY value DESC LIMIT 5;

-- Most Strikeouts (batting)
SELECT 'XIP - Most K (batting)' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.bat_strike_outs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE g.innings_played > 9
ORDER BY pgs.bat_strike_outs DESC LIMIT 5;

-- Most Strikeouts (pitching)
SELECT 'XIP - Most K (pitching)' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_strike_outs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played > 9
ORDER BY pgs.pitch_strike_outs DESC LIMIT 5;

-- Most Innings Pitched
SELECT 'XIP - Most IP' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    (pgs.pitch_outs / 3) || '.' || (pgs.pitch_outs % 3) as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played > 9
ORDER BY pgs.pitch_outs DESC LIMIT 5;

-- Most Walks Allowed
SELECT 'XIP - Most BB allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_walks as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played > 9
ORDER BY pgs.pitch_walks DESC LIMIT 5;

-- Most HR Allowed
SELECT 'XIP - Most HR allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_home_runs as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played > 9
ORDER BY pgs.pitch_home_runs DESC LIMIT 5;

-- Most Hits Allowed
SELECT 'XIP - Most H allowed' as record,
    p.first_name || ' ' || p.last_name as player,
    t.city || ' ' || t.mascot as team,
    g.date, s.year as season,
    pgs.pitch_hits as value,
    g.innings_played as innings
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.id
JOIN teams t ON pgs.team_id = t.id
JOIN games g ON pgs.game_id = g.id
JOIN seasons s ON g.season_id = s.id
WHERE pgs.pitch_game_played = 1
  AND g.innings_played > 9
ORDER BY pgs.pitch_hits DESC LIMIT 5;
