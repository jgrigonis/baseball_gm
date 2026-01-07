# SCHEMA_SQL always represents the final schema

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    bats TEXT,
    throws TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    mascot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    team_id   TEXT NOT NULL,
    player_id TEXT NOT NULL,

    PRIMARY KEY (team_id, player_id),

    FOREIGN KEY (team_id) REFERENCES teams(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS league_teams (
    league_id TEXT NOT NULL,
    team_id TEXT NOT NULL,

    PRIMARY KEY (league_id, team_id),

    FOREIGN KEY (team_id) REFERENCES teams(id),
    FOREIGN KEY (league_id) REFERENCES leagues(league_id)    
);

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    year INTEGER,
    name TEXT      -- e.g. "Season1"
);

CREATE TABLE IF NOT EXISTS leagues (
    league_id TEXT PRIMARY KEY,
    league_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    name TEXT NOT NULL,     -- "Season1ALCS"
    FOREIGN KEY (season_id) REFERENCES seasons(id)
);

CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,          -- ISO date
    season_id TEXT NOT NULL,
    series_id TEXT,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,

    FOREIGN KEY (season_id) REFERENCES seasons(id),
    FOREIGN KEY (series_id) REFERENCES series(id),
    FOREIGN KEY (home_team_id) REFERENCES teams(id),
    FOREIGN KEY (away_team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    opponent_team_id TEXT NOT NULL,

    -- Batting
    bat_ab INTEGER,
    bat_hits INTEGER,
    bat_doubles INTEGER,
    bat_triples INTEGER,
    bat_home_runs INTEGER,
    bat_rbi INTEGER,
    bat_runs INTEGER,
    bat_walks INTEGER,
    bat_strike_outs INTEGER,
    bat_hbp INTEGER,
    bat_sac_flys INTEGER,
    bat_sac_bunts INTEGER,
    bat_gdp INTEGER,
    bat_gtp INTEGER,
    bat_stolen_bases INTEGER,
    bat_caught_stealing INTEGER,
    bat_pickoffs INTEGER,

    -- Pitching
    pitch_outs INTEGER,
    pitch_hits INTEGER,
    pitch_runs INTEGER,
    pitch_home_runs INTEGER,
    pitch_walks INTEGER,
    pitch_strike_outs INTEGER,
    pitch_hit_batters INTEGER,
    pitch_doubles INTEGER DEFAULT 0,
    pitch_triples INTEGER DEFAULT 0,
    pitch_pickoffs INTEGER DEFAULT 0,
    pitch_balks INTEGER DEFAULT 0,
    pitch_wild_pitches INTEGER DEFAULT 0,
    pitch_count INTEGER,

    -- Fielding
    field_putouts INTEGER,
    field_assists INTEGER,
    field_errors INTEGER,
    -- field_chances INTEGER,

    PRIMARY KEY (game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    runs INTEGER,
    hits INTEGER,
    errors INTEGER,
    win INTEGER,     -- 1 or 0
    loss INTEGER,    -- 1 or 0

    PRIMARY KEY (game_id, team_id),
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (team_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS pitcher_state (
    player_id TEXT PRIMARY KEY,
    current_energy REAL NOT NULL,
    last_game_date TEXT,
    last_pitch_count INTEGER,

    FOREIGN KEY (player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS plate_appearances (
    id TEXT PRIMARY KEY,
    game_id TEXT,
    inning INTEGER,
    batter_id TEXT,
    pitcher_id TEXT,
    result TEXT,
    rbi INTEGER
);

"""
