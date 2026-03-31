# src/db/schema.py
# SCHEMA_SQL always represents the final schema

from src.team.team_in_game import Position

_positions = ", ".join(f"'{p.value}'" for p in Position)
POSITION_CHECK = f"CHECK (position IN ({_positions}))"

SCHEMA_SQL = f"""
-- Enable foreign key enforcement (must be set per connection)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS players (
    id         TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    bats       TEXT NOT NULL,
    throws     TEXT NOT NULL,
    position   TEXT,  -- Affinity position used in creation, can be NULL
    league_id  TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS player_skills (
    player_id TEXT PRIMARY KEY,
    
    age INTEGER NOT NULL DEFAULT 17,
    durability INTEGER NOT NULL,
    clutch INTEGER NOT NULL,
    speed INTEGER NOT NULL,
    power INTEGER NOT NULL,
    eye INTEGER NOT NULL,
    contact INTEGER NOT NULL,
    base_running INTEGER NOT NULL,
    bunting INTEGER NOT NULL,
    catching INTEGER NOT NULL,
    infield INTEGER NOT NULL,
    outfield INTEGER NOT NULL,
    arm INTEGER NOT NULL,
    accuracy INTEGER NOT NULL,
    stamina INTEGER NOT NULL,
    recovery INTEGER NOT NULL,
    ground_balls INTEGER NOT NULL,
    strikes INTEGER NOT NULL,
    
    updated_at TEXT,
    
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_talent_caps (
    player_id    TEXT PRIMARY KEY,

    -- Hitting
    clutch       INTEGER NOT NULL DEFAULT 100 CHECK (clutch       BETWEEN 1 AND 100),
    speed        INTEGER NOT NULL DEFAULT 100 CHECK (speed        BETWEEN 1 AND 100),
    durability   INTEGER NOT NULL DEFAULT 100 CHECK (durability   BETWEEN 1 AND 100),
    power        INTEGER NOT NULL DEFAULT 100 CHECK (power        BETWEEN 1 AND 100),
    eye          INTEGER NOT NULL DEFAULT 100 CHECK (eye          BETWEEN 1 AND 100),
    contact      INTEGER NOT NULL DEFAULT 100 CHECK (contact      BETWEEN 1 AND 100),
    base_running INTEGER NOT NULL DEFAULT 100 CHECK (base_running BETWEEN 1 AND 100),
    bunting      INTEGER NOT NULL DEFAULT 100 CHECK (bunting      BETWEEN 1 AND 100),

    -- Defense
    catching     INTEGER NOT NULL DEFAULT 100 CHECK (catching     BETWEEN 1 AND 100),
    infield      INTEGER NOT NULL DEFAULT 100 CHECK (infield      BETWEEN 1 AND 100),
    outfield     INTEGER NOT NULL DEFAULT 100 CHECK (outfield     BETWEEN 1 AND 100),
    arm          INTEGER NOT NULL DEFAULT 100 CHECK (arm          BETWEEN 1 AND 100),

    -- Pitching
    accuracy     INTEGER NOT NULL DEFAULT 100 CHECK (accuracy     BETWEEN 1 AND 100),
    stamina      INTEGER NOT NULL DEFAULT 100 CHECK (stamina      BETWEEN 1 AND 100),
    recovery     INTEGER NOT NULL DEFAULT 100 CHECK (recovery     BETWEEN 1 AND 100),
    ground_balls INTEGER NOT NULL DEFAULT 100 CHECK (ground_balls BETWEEN 1 AND 100),
    strikes      INTEGER NOT NULL DEFAULT 100 CHECK (strikes      BETWEEN 1 AND 100),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Track skill progression over time
CREATE TABLE IF NOT EXISTS player_skills_history (
    player_id    TEXT NOT NULL,
    season_id    TEXT NOT NULL,

    age          INTEGER NOT NULL DEFAULT 17,
    durability   INTEGER NOT NULL,
    clutch       INTEGER NOT NULL,
    speed        INTEGER NOT NULL,
    power        INTEGER NOT NULL,
    eye          INTEGER NOT NULL,
    contact      INTEGER NOT NULL,
    base_running INTEGER NOT NULL,
    bunting      INTEGER NOT NULL,
    catching     INTEGER NOT NULL,
    infield      INTEGER NOT NULL,
    outfield     INTEGER NOT NULL,
    arm          INTEGER NOT NULL,
    accuracy     INTEGER NOT NULL,
    stamina      INTEGER NOT NULL,
    recovery     INTEGER NOT NULL,
    ground_balls INTEGER NOT NULL,
    strikes      INTEGER NOT NULL,
    
    recorded_at  TEXT NOT NULL,
    
    PRIMARY KEY (player_id, season_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_status (
    player_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect'
    )),
    since TEXT NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_energy (
    player_id            TEXT NOT NULL,
    league_id            TEXT NOT NULL DEFAULT '',
    current_energy       REAL NOT NULL DEFAULT 1.0 CHECK (current_energy >= 0.0 AND current_energy <= 1.0),
    max_energy           REAL NOT NULL DEFAULT 1.0 CHECK (max_energy >= 0.0 AND max_energy <= 1.0),
    last_game_date       TEXT,                                    -- ISO date of last game played
    consecutive_days     INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_days >= 0),
    season_games_played  INTEGER NOT NULL DEFAULT 0 CHECK (season_games_played >= 0),

    PRIMARY KEY (player_id, league_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_injuries (
    player_id               TEXT NOT NULL,
    league_id               TEXT NOT NULL DEFAULT '',
    games_remaining         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, league_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_injury_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       TEXT NOT NULL,
    season_id       TEXT,                   -- nullable for pre-season injuries
    injury_date     TEXT NOT NULL,
    severity        TEXT NOT NULL,
    activity        TEXT,
    games_missed    INTEGER NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Track completed offseason steps for each season
CREATE TABLE IF NOT EXISTS offseason_steps (
    season_id TEXT NOT NULL,
    step TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (season_id, step),
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_rotations (
    team_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    rotation_order INTEGER NOT NULL,
    effective_date TEXT NOT NULL,  -- When this rotation assignment started
    end_date TEXT,                 -- NULL = currently active
    
    PRIMARY KEY (team_id, season_id, player_id, effective_date),
    
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS bullpen_roles (
    team_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Closer', 'Setup', 'Middle', 'Long', 'Specialist', 'Utility')),
    effective_date TEXT NOT NULL,
    end_date TEXT,  -- NULL = currently active

    PRIMARY KEY (team_id, player_id, season_id, effective_date),

    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_lineup_slots (
    game_id       TEXT NOT NULL,
    team_id       TEXT NOT NULL,
    player_id     TEXT NOT NULL,
    position      TEXT NOT NULL,
    batting_order INTEGER,          -- NULL for starting pitcher
    is_pitcher    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, team_id, player_id),
    FOREIGN KEY (game_id)   REFERENCES games(id)   ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    mascot TEXT NOT NULL,
    source_csv TEXT,
    source_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS team_players (
    team_id   TEXT NOT NULL,
    player_id TEXT NOT NULL,

    PRIMARY KEY (team_id, player_id),

    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    year INTEGER,
    name TEXT,      -- e.g. "Season1"
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leagues (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,

    -- GM layer fields
    join_code            TEXT UNIQUE,
    mode                 TEXT NOT NULL DEFAULT 'blitz'
                             CHECK (mode IN ('blitz', 'longform')),
    num_teams            INTEGER NOT NULL DEFAULT 30,
    decision_window_sec  INTEGER NOT NULL DEFAULT 120,
    reentry_enabled      INTEGER NOT NULL DEFAULT 1
                             CHECK (reentry_enabled IN (0, 1)),
    pace_control         TEXT NOT NULL DEFAULT 'timer'
                             CHECK (pace_control IN ('timer', 'confirmed', 'scheduled')),
    state                TEXT NOT NULL DEFAULT 'lobby'
                             CHECK (state IN (
                                 'lobby', 'draft', 'preseason', 'season',
                                 'playoffs', 'offseason', 'complete'
                             )),
    commissioner_gm_id   TEXT,
    draft_window_sec     INTEGER NOT NULL DEFAULT 300,
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (commissioner_gm_id) REFERENCES gms(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS league_seasons (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    
    PRIMARY KEY (league_id, season_id),
    
    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS league_season_teams (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    
    PRIMARY KEY (league_id, season_id, team_id),
    
    FOREIGN KEY (league_id, season_id) REFERENCES league_seasons(league_id, season_id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    name TEXT NOT NULL,     -- "Season1ALCS"
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    game_date TEXT NOT NULL,          -- ISO date
    season_id TEXT NOT NULL,
    series_id TEXT,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    completed INTEGER DEFAULT 0,
    innings_played INTEGER,
    winner_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,

    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE SET NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (away_team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id       TEXT    NOT NULL,
    inning        INTEGER,
    half          TEXT    CHECK (half IN ('top', 'bottom', NULL)),
    team_id       TEXT    NOT NULL,
    event_type    TEXT    NOT NULL CHECK (event_type IN (
                      'lineup_set',
                      'pitcher_start',
                      'pitching_change',
                      'closer_called',
                      'injury',
                      'substitution'
                  )),
    player_id     TEXT,           -- primary player involved
    player_id_2   TEXT,           -- secondary player (e.g. who was replaced)
    reason        TEXT,           -- human-readable explanation
    detail        TEXT,           -- JSON for structured data (lineup slots, etc.)
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
 
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    opponent_team_id TEXT NOT NULL,

    -- Batting
    bat_game_played INTEGER DEFAULT 1 CHECK (bat_game_played IN (0, 1)),
    bat_game_started INTEGER DEFAULT 0 CHECK (bat_game_started IN (0, 1)),
    bat_ab INTEGER CHECK (bat_ab >= 0),
    bat_hits INTEGER CHECK (bat_hits >= 0),
    bat_doubles INTEGER CHECK (bat_doubles >= 0),
    bat_triples INTEGER CHECK (bat_triples >= 0),
    bat_home_runs INTEGER CHECK (bat_home_runs >= 0),
    bat_rbi INTEGER CHECK (bat_rbi >= 0),
    bat_runs INTEGER CHECK (bat_runs >= 0),
    bat_walks INTEGER CHECK (bat_walks >= 0),
    bat_strike_outs INTEGER CHECK (bat_strike_outs >= 0),
    bat_hbp INTEGER CHECK (bat_hbp >= 0),
    bat_sac_flys INTEGER CHECK (bat_sac_flys >= 0),
    bat_sac_bunts INTEGER CHECK (bat_sac_bunts >= 0),
    bat_gdp INTEGER CHECK (bat_gdp >= 0),
    bat_gtp INTEGER CHECK (bat_gtp >= 0),
    bat_stolen_bases INTEGER CHECK (bat_stolen_bases >= 0),
    bat_caught_stealing INTEGER CHECK (bat_caught_stealing >= 0),

    -- Pitching
    pitch_game_played INTEGER DEFAULT 0 CHECK (pitch_game_played IN (0, 1)),
    pitch_game_started INTEGER DEFAULT 0 CHECK (pitch_game_started IN (0, 1)),
    pitch_complete_game INTEGER DEFAULT 0 CHECK (pitch_complete_game IN (0, 1)),
    pitch_shutout INTEGER DEFAULT 0 CHECK (pitch_shutout IN (0, 1)),
    pitch_win INTEGER DEFAULT 0 CHECK (pitch_win IN (0, 1)),
    pitch_loss INTEGER DEFAULT 0 CHECK (pitch_loss IN (0, 1)),
    pitch_save INTEGER DEFAULT 0 CHECK (pitch_save IN (0, 1)),
    pitch_hold INTEGER DEFAULT 0 CHECK (pitch_hold IN (0, 1)),
    pitch_outs INTEGER CHECK (pitch_outs >= 0),
    pitch_hits INTEGER CHECK (pitch_hits >= 0),
    pitch_runs INTEGER CHECK (pitch_runs >= 0),
    pitch_earned_runs INTEGER CHECK (pitch_earned_runs >= 0),
    pitch_home_runs INTEGER CHECK (pitch_home_runs >= 0),
    pitch_walks INTEGER CHECK (pitch_walks >= 0),
    pitch_strike_outs INTEGER CHECK (pitch_strike_outs >= 0),
    pitch_hit_batters INTEGER CHECK (pitch_hit_batters >= 0),
    pitch_doubles INTEGER DEFAULT 0 CHECK (pitch_doubles >= 0),
    pitch_triples INTEGER DEFAULT 0 CHECK (pitch_triples >= 0),
    pitch_pickoffs INTEGER DEFAULT 0 CHECK (pitch_pickoffs >= 0),
    pitch_balks INTEGER DEFAULT 0 CHECK (pitch_balks >= 0),
    pitch_wild_pitches INTEGER DEFAULT 0 CHECK (pitch_wild_pitches >= 0),
    pitch_count INTEGER CHECK (pitch_count >= 0),

    -- Fielding
    field_putouts INTEGER CHECK (field_putouts >= 0),
    field_assists INTEGER CHECK (field_assists >= 0),
    field_errors INTEGER CHECK (field_errors >= 0),
    passed_balls INTEGER CHECK (passed_balls >= 0),
    catcher_interferences INTEGER CHECK (catcher_interferences >= 0),
    catcher_cs INTEGER CHECK (catcher_cs >= 0),
    catcher_sb INTEGER CHECK (catcher_sb >= 0),

    PRIMARY KEY (game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       TEXT    NOT NULL,
    season_id       TEXT    NOT NULL,
    team_id         TEXT    NOT NULL,
    is_postseason   INTEGER NOT NULL DEFAULT 0 CHECK (is_postseason IN (0, 1)),
 
    -- ── Batting ──────────────────────────────────────────────────────────────
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
 
    -- ── Pitching ─────────────────────────────────────────────────────────────
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
 
    -- ── Fielding ─────────────────────────────────────────────────────────────
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

CREATE TABLE IF NOT EXISTS player_game_fielding (
    game_id    TEXT NOT NULL,
    player_id  TEXT NOT NULL,
    position   TEXT NOT NULL {POSITION_CHECK},

    putouts               INTEGER DEFAULT 0 CHECK (putouts >= 0),
    assists               INTEGER DEFAULT 0 CHECK (assists >= 0),
    errors                INTEGER DEFAULT 0 CHECK (errors >= 0),
    passed_balls          INTEGER CHECK (passed_balls >= 0),
    catcher_interferences INTEGER CHECK (catcher_interferences >= 0),
    catcher_cs            INTEGER CHECK (catcher_cs >= 0),
    catcher_sb            INTEGER CHECK (catcher_sb >= 0),

    PRIMARY KEY (game_id, player_id, position),

    FOREIGN KEY (game_id)   REFERENCES games(id)   ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    runs INTEGER CHECK (runs >= 0),
    hits INTEGER CHECK (hits >= 0),
    errors INTEGER CHECK (errors >= 0),
    win INTEGER CHECK (win IN (0, 1)) NOT NULL DEFAULT 0,     -- 1 or 0
    loss INTEGER CHECK (loss IN (0, 1)) NOT NULL DEFAULT 0,    -- 1 or 0

    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pitcher_state (
    player_id            TEXT NOT NULL,
    league_id            TEXT NOT NULL DEFAULT '',
    current_energy       REAL NOT NULL CHECK (current_energy >= 0.0 AND current_energy <= 1.0),
    max_energy           REAL NOT NULL DEFAULT 1.0 CHECK (max_energy >= 0.0 AND max_energy <= 1.0),
    consecutive_days     INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_days >= 0),
    last_game_date       TEXT,
    last_pitch_count     INTEGER CHECK (last_pitch_count >= 0),

    PRIMARY KEY (player_id, league_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- ── GM / Identity layer ───────────────────────────────────────────────────────
--
-- users: one row per human across all leagues and sessions.
--   session_token is the opaque credential stored in the browser cookie.
--   A future login system would link a new token to an existing user row.
--
-- gms: one row per user per league (plus one per AI slot).
--   user_id is NULL for AI GMs.
--   All league-specific state (team, performance, fired status) lives here.
--   The API resolves identity as: session_token → user → gms WHERE league_id = ?

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    session_token TEXT UNIQUE NOT NULL,   -- credential stored in browser cookie
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gms (
    id             TEXT PRIMARY KEY,
    league_id      TEXT NOT NULL,
    user_id        TEXT,                  -- NULL for AI GMs
    team_id        TEXT,                  -- NULL until assigned
    display_name   TEXT NOT NULL,         -- can differ from users.display_name per league
    is_ai          INTEGER NOT NULL DEFAULT 0 CHECK (is_ai   IN (0, 1)),
    is_away        INTEGER NOT NULL DEFAULT 0 CHECK (is_away IN (0, 1)),
    career_seasons INTEGER NOT NULL DEFAULT 0,
    warned_at      TEXT,                  -- ISO datetime of performance warning
    fired_at       TEXT,                  -- ISO datetime of firing; NULL = active
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE SET NULL,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS gm_lineup_preferences (
    gm_id        TEXT NOT NULL,
    player_id    TEXT NOT NULL,
    batting_order INTEGER,        -- 1-9, NULL for bench/pitcher
    position     TEXT,            -- defensive position
    is_starter   INTEGER NOT NULL DEFAULT 1
                        CHECK (is_starter IN (0, 1)),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),

    PRIMARY KEY (gm_id, player_id),

    FOREIGN KEY (gm_id)     REFERENCES gms(id)     ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- One row per GM, created on join, mutable between series.
CREATE TABLE IF NOT EXISTS gm_profiles (
    gm_id TEXT PRIMARY KEY,

    -- Batting tendencies
    lineup_style     TEXT NOT NULL DEFAULT 'traditional'
                         CHECK (lineup_style     IN ('traditional', 'analytics', 'speed-first', 'power-first')),
    steal_aggression TEXT NOT NULL DEFAULT 'standard'
                         CHECK (steal_aggression IN ('conservative', 'standard', 'aggressive')),
    sac_bunt         TEXT NOT NULL DEFAULT 'situational'
                         CHECK (sac_bunt         IN ('never', 'situational', 'frequent')),

    -- Pitching tendencies
    starter_usage TEXT NOT NULL DEFAULT 'pitch-count-strict'
                      CHECK (starter_usage IN ('let-them-work', 'pitch-count-strict', 'matchup-based')),
    closer_usage  TEXT NOT NULL DEFAULT 'saves-only'
                      CHECK (closer_usage  IN ('saves-only', 'high-leverage', 'best-available')),
    bullpen_pref  TEXT NOT NULL DEFAULT 'deep-pen'
                      CHECK (bullpen_pref  IN ('deep-pen', 'starter-heavy')),

    -- Roster tendencies
    platoon_usage TEXT NOT NULL DEFAULT 'none'
                      CHECK (platoon_usage IN ('none', 'vs-handedness', 'aggressive')),

    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (gm_id) REFERENCES gms(id) ON DELETE CASCADE
);

-- One draft per league per season.
CREATE TABLE IF NOT EXISTS drafts (
    id             TEXT PRIMARY KEY,
    league_id      TEXT NOT NULL,
    season_id      TEXT NOT NULL,
    format         TEXT NOT NULL CHECK (format IN ('preference', 'interactive')),
    state          TEXT NOT NULL DEFAULT 'pending'
                       CHECK (state IN ('pending', 'open', 'complete')),
    current_pick   INTEGER NOT NULL DEFAULT 1,
    pick_timer_sec INTEGER NOT NULL DEFAULT 90,  -- interactive drafts only

    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE (league_id, season_id),

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- Written as the draft runs; snake order derived from pick_number + num_teams.
CREATE TABLE IF NOT EXISTS draft_picks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id    TEXT    NOT NULL,
    pick_number INTEGER NOT NULL,   -- 1-based absolute pick across all rounds
    round       INTEGER NOT NULL,
    gm_id       TEXT    NOT NULL,
    team_id     TEXT    NOT NULL,
    player_id   TEXT    NOT NULL,
    auto_picked INTEGER NOT NULL DEFAULT 0 CHECK (auto_picked IN (0, 1)),
    picked_at   TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE (draft_id, pick_number),
    UNIQUE (draft_id, player_id),   -- each player picked at most once

    FOREIGN KEY (draft_id)  REFERENCES drafts(id)  ON DELETE CASCADE,
    FOREIGN KEY (gm_id)     REFERENCES gms(id),
    FOREIGN KEY (team_id)   REFERENCES teams(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);

-- Blitz: primary mechanism. Longform: fallback when pick timer expires.
CREATE TABLE IF NOT EXISTS draft_preferences (
    gm_id     TEXT    NOT NULL,
    draft_id  TEXT    NOT NULL,
    player_id TEXT    NOT NULL,
    rank      INTEGER NOT NULL,  -- lower = higher preference

    PRIMARY KEY (gm_id, draft_id, player_id),
    UNIQUE      (gm_id, draft_id, rank),  -- no ties within a list

    FOREIGN KEY (gm_id)     REFERENCES gms(id)     ON DELETE CASCADE,
    FOREIGN KEY (draft_id)  REFERENCES drafts(id)  ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Written at season end by the evaluation job.
CREATE TABLE IF NOT EXISTS gm_season_evaluations (
    gm_id                 TEXT NOT NULL,
    season_id             TEXT NOT NULL,
    wins                  INTEGER NOT NULL DEFAULT 0,
    losses                INTEGER NOT NULL DEFAULT 0,
    expected_wins         REAL,
    roster_quality_rating REAL,
    made_playoffs         INTEGER NOT NULL DEFAULT 0 CHECK (made_playoffs    IN (0, 1)),
    won_championship      INTEGER NOT NULL DEFAULT 0 CHECK (won_championship IN (0, 1)),
    verdict               TEXT CHECK (verdict IN ('retained', 'warned', 'fired')),
    evaluated_at          TEXT NOT NULL DEFAULT (datetime('now')),

    PRIMARY KEY (gm_id, season_id),

    FOREIGN KEY (gm_id)     REFERENCES gms(id)     ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_player_skills_player_id ON player_skills(player_id);
CREATE INDEX IF NOT EXISTS idx_player_skills_history_player ON player_skills_history(player_id);
CREATE INDEX IF NOT EXISTS idx_player_skills_history_season ON player_skills_history(season_id);
CREATE INDEX IF NOT EXISTS idx_injury_log_player ON player_injury_log(player_id);
CREATE INDEX IF NOT EXISTS idx_injury_log_season ON player_injury_log(season_id);
CREATE INDEX IF NOT EXISTS idx_talent_caps_player ON player_talent_caps(player_id);
CREATE INDEX IF NOT EXISTS idx_player_status_status ON player_status(status);
CREATE INDEX IF NOT EXISTS idx_player_energy_player ON player_energy(player_id);
CREATE INDEX IF NOT EXISTS idx_team_players_team ON team_players(team_id);
CREATE INDEX IF NOT EXISTS idx_team_players_player ON team_players(player_id);
CREATE INDEX IF NOT EXISTS idx_league_season_teams_league_season ON league_season_teams(league_id, season_id);
CREATE INDEX IF NOT EXISTS idx_league_season_teams_team ON league_season_teams(team_id);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season_id);
CREATE INDEX IF NOT EXISTS idx_games_home_team ON games(home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away_team ON games(away_team_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_game ON player_game_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_player ON player_game_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_team_game_stats_game ON team_game_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_team_game_stats_team ON team_game_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_bullpen_roles_team_season ON bullpen_roles(team_id, season_id);
CREATE INDEX IF NOT EXISTS idx_bullpen_roles_player ON bullpen_roles(player_id);
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
CREATE INDEX IF NOT EXISTS idx_pgs_player_bat
    ON player_game_stats(player_id, bat_game_played);
CREATE INDEX IF NOT EXISTS idx_pgs_player_pitch
    ON player_game_stats(player_id, pitch_game_played);
CREATE INDEX IF NOT EXISTS idx_pgs_game_bat
    ON player_game_stats(game_id, bat_game_played);
CREATE INDEX IF NOT EXISTS idx_pgs_game_pitch
    ON player_game_stats(game_id, pitch_game_played);
CREATE INDEX IF NOT EXISTS idx_pgs_player_team
    ON player_game_stats(player_id, team_id);
CREATE INDEX IF NOT EXISTS idx_pss_season_postseason
    ON player_season_stats(season_id, is_postseason);
CREATE INDEX IF NOT EXISTS idx_pss_player_season
    ON player_season_stats(player_id, season_id);
CREATE INDEX IF NOT EXISTS idx_pss_team_season
    ON player_season_stats(team_id, season_id);

-- GM / identity layer indexes
CREATE INDEX IF NOT EXISTS idx_users_session        ON users(session_token);
CREATE INDEX IF NOT EXISTS idx_gms_league           ON gms(league_id);
CREATE INDEX IF NOT EXISTS idx_gms_user             ON gms(user_id);
CREATE INDEX IF NOT EXISTS idx_gms_team             ON gms(team_id);
CREATE INDEX IF NOT EXISTS idx_leagues_join_code    ON leagues(join_code);
CREATE INDEX IF NOT EXISTS idx_drafts_league_season ON drafts(league_id, season_id);
CREATE INDEX IF NOT EXISTS idx_draft_picks_draft    ON draft_picks(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_picks_gm       ON draft_picks(gm_id);
CREATE INDEX IF NOT EXISTS idx_draft_picks_player   ON draft_picks(player_id);
CREATE INDEX IF NOT EXISTS idx_draft_prefs_gm_draft ON draft_preferences(gm_id, draft_id);
CREATE INDEX IF NOT EXISTS idx_gm_evals_season      ON gm_season_evaluations(season_id);
CREATE INDEX IF NOT EXISTS idx_lineup_pref_gm       ON gm_lineup_preferences(gm_id);
CREATE INDEX IF NOT EXISTS idx_players_league       ON players(league_id);

-- Game Events indexes
CREATE INDEX IF NOT EXISTS idx_game_events_game
    ON game_events(game_id);
 
CREATE INDEX IF NOT EXISTS idx_game_events_type
    ON game_events(game_id, event_type);
 
CREATE INDEX IF NOT EXISTS idx_game_events_player
    ON game_events(player_id);
"""
