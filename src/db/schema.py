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
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    bats TEXT NOT NULL,
    throws TEXT NOT NULL,
    position TEXT,  -- Affinity position used in creation, can be NULL
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS player_skills (
    player_id TEXT PRIMARY KEY,
    
    age INTEGER NOT NULL DEFAULT 17,
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
    player_id            TEXT PRIMARY KEY,
    current_energy       REAL NOT NULL DEFAULT 1.0 CHECK (current_energy >= 0.0 AND current_energy <= 1.0),
    injuries_this_season INTEGER NOT NULL DEFAULT 0,
    last_game_date       TEXT,                                    -- ISO date of last game played
    consecutive_days     INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_days >= 0),
    season_games_played  INTEGER NOT NULL DEFAULT 0 CHECK (season_games_played >= 0),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_injuries (
    player_id               TEXT PRIMARY KEY,
    games_remaining         INTEGER NOT NULL DEFAULT 0,
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
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
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
    date TEXT NOT NULL,          -- ISO date
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
    win INTEGER CHECK (win IN (0, 1)),     -- 1 or 0
    loss INTEGER CHECK (loss IN (0, 1)),    -- 1 or 0

    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pitcher_state (
    player_id TEXT PRIMARY KEY,
    current_energy REAL NOT NULL CHECK (current_energy >= 0),
    last_game_date TEXT,
    last_pitch_count INTEGER CHECK (last_pitch_count >= 0),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_player_skills_player_id ON player_skills(player_id);
CREATE INDEX IF NOT EXISTS idx_player_skills_history_player ON player_skills_history(player_id);
CREATE INDEX IF NOT EXISTS idx_player_skills_history_season ON player_skills_history(season_id);
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
"""
