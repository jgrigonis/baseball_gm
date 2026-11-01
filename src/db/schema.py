# src/db/schema.py
# SCHEMA_SQL always represents the final schema

from src.team.team_in_game import Position

_positions = ", ".join(f"'{p.value}'" for p in Position)
POSITION_CHECK = f"CHECK (position IN ({_positions}))"

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS leagues (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,

    -- GM layer fields
    join_code            TEXT UNIQUE,
    mode                 TEXT NOT NULL DEFAULT 'blitz'
                             CHECK (mode IN ('blitz', 'speed_blitz', 'longform')),
    num_teams            INTEGER NOT NULL DEFAULT 30,
    decision_window_sec  INTEGER NOT NULL DEFAULT 120,
    reentry_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    pace_control         TEXT NOT NULL DEFAULT 'timer'
                             CHECK (pace_control IN ('timer', 'confirmed', 'scheduled')),
    state                TEXT NOT NULL DEFAULT 'lobby'
                             CHECK (state IN (
                                 'lobby', 'draft', 'preseason', 'season',
                                 'playoffs', 'offseason', 'complete'
                             )),
    commissioner_gm_id   TEXT,
    draft_window_sec     INTEGER NOT NULL DEFAULT 300,
    lineup_window_sec    INTEGER NOT NULL DEFAULT 600,  -- the first period after the draft

    -- Ready-check (multiplayer). A GM is ready when gms.ready_period equals
    -- sim_period; moving to the next period un-readies everyone at once.
    sim_period           INTEGER NOT NULL DEFAULT 0,
    period_deadline      TIMESTAMPTZ,      -- end of the Decision Window (timer pace)
    sim_period_days      INTEGER NOT NULL DEFAULT 3,  -- season days per period
    num_seasons          INTEGER NOT NULL DEFAULT 10, -- how many seasons the league runs
    last_played_at       TIMESTAMPTZ,      -- last real-world time games were played or the league moved on
    is_public            BOOLEAN NOT NULL DEFAULT FALSE, -- listed under Public Leagues
    is_paused            BOOLEAN NOT NULL DEFAULT FALSE, -- an admin stopped it moving on
    is_practice          BOOLEAN NOT NULL DEFAULT FALSE, -- a solo tutorial league
    coach_done           TEXT[] NOT NULL DEFAULT '{{}}',   -- coach steps done (src/api/services/coach.py)
    trade_vote           BOOLEAN NOT NULL DEFAULT TRUE,  -- other GMs vote on trades between GMs
    stop_for_trade_offers BOOLEAN NOT NULL DEFAULT TRUE, -- single player: sims stop for an offer
    pick_trades          BOOLEAN NOT NULL DEFAULT FALSE, -- teams can trade draft picks
    injuries_enabled     BOOLEAN NOT NULL DEFAULT TRUE,  -- players can get hurt (off by default in Speed Blitz)
    backstory_years      INTEGER NOT NULL DEFAULT 5,     -- past seasons generated at the start (src/league/backstory/)
    weighted_schedule    BOOLEAN NOT NULL DEFAULT FALSE, -- division rivals play more often (src/league/weighted_schedule.py)
    created_at TEXT DEFAULT (NOW())
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version BIGINT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    year INTEGER,
    name TEXT,      -- e.g. "Season1"
    is_backstory BOOLEAN NOT NULL DEFAULT FALSE,  -- generated before the league started (src/league/backstory/)
    created_at TEXT DEFAULT (NOW())
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    mascot TEXT NOT NULL,
    source_csv TEXT,
    source_hash TEXT,
    created_at TEXT DEFAULT (NOW()),
    updated_at TEXT
);

-- users: one row per human across all leagues and sessions.
--   session_token is the opaque credential stored in the browser cookie.
--   username + password_hash are the login. Both are NULL for guests created
--   before passwords existed; those users set them on their next visit.
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    session_token TEXT UNIQUE NOT NULL,   
    display_name  TEXT NOT NULL,
    username      TEXT,                   -- unique ignoring case (index in migration 003)
    password_hash TEXT,                   -- argon2id
    email         TEXT UNIQUE,
    is_verified   BOOLEAN NOT NULL DEFAULT FALSE,
    totp_secret   TEXT,
    is_admin      BOOLEAN NOT NULL DEFAULT FALSE, -- can open /admin/
    is_contributor BOOLEAN NOT NULL DEFAULT FALSE, -- paid for the game (Paid contributor badge)
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_tips TEXT[] NOT NULL DEFAULT '{{}}', -- first-visit tab tips closed
    created_at    TEXT NOT NULL DEFAULT (NOW())
);

-- password_resets: one row per emailed reset link. Only a SHA-256 hash of the
--   token is kept. A link works for an hour, once (migration 016).
CREATE TABLE IF NOT EXISTS password_resets (
    id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT UNIQUE NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ,
    requested_ip TEXT
);

-- login_failures: one row per wrong password at sign-in, so repeated guesses
--   are turned away for a while. username is lowercased (migration 017).
CREATE TABLE IF NOT EXISTS login_failures (
    id         BIGSERIAL PRIMARY KEY,
    username   TEXT NOT NULL,
    ip         TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- sim_jobs: work that moves a league on (simming days, the playoffs, the
--   offseason, the draft, starting the league, a ready-check period), queued
--   by the web server and run by the sim worker (src/worker.py), so no web
--   request waits on it. At most one job per league is queued or running.
CREATE TABLE IF NOT EXISTS sim_jobs (
    id              TEXT PRIMARY KEY,
    league_id       TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    params          JSONB NOT NULL DEFAULT '{{}}',
    gm_id           TEXT,             -- who asked for it; NULL for a ready-check period
    state           TEXT NOT NULL DEFAULT 'queued'
                        CHECK (state IN ('queued', 'running', 'done', 'failed')),
    result          JSONB,
    error           TEXT,             -- shown to the GM when state is 'failed'
    attempts        INTEGER NOT NULL DEFAULT 0, -- times the worker found the league locked
    run_after       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    heartbeat_at    TIMESTAMPTZ,      -- the worker running it is still alive
    finished_at     TIMESTAMPTZ
);

-- 1 row per player
CREATE TABLE IF NOT EXISTS players (
    id         TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    bats       TEXT NOT NULL,
    throws     TEXT NOT NULL,
    position   TEXT,  -- Affinity position used in creation, can be NULL
    league_id  TEXT,
    created_at TEXT DEFAULT (NOW()),
    updated_at TEXT,

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE SET NULL
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

    created_at TEXT NOT NULL DEFAULT (NOW()),

    UNIQUE (league_id, season_id),

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS league_seasons (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    
    PRIMARY KEY (league_id, season_id),
    
    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- Track completed offseason steps for each season
CREATE TABLE IF NOT EXISTS offseason_steps (
    season_id TEXT NOT NULL,
    step TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (season_id, step),
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    name TEXT NOT NULL,     -- "Season1ALCS"
    created_at TEXT DEFAULT (NOW()),
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- ── Draft order & pick rights ────────────────────────────────────────────────

-- Records the finalized pick order for each executed draft.
-- Written once by the offseason pipeline, never mutated.
-- Tracks current ownership of each pick slot.
-- Written by the pipeline alongside draft_order.
-- current_owner_id == original_team_id until a trade changes it.
-- draft_year + league_id identify the draft without requiring a draft_id FK,
-- allowing future-season picks to be traded before the draft record exists.
CREATE TABLE IF NOT EXISTS draft_pick_rights (
    league_id         TEXT    NOT NULL,
    draft_year        INTEGER NOT NULL,
    round             INTEGER NOT NULL,
    original_team_id  TEXT    NOT NULL,
    current_owner_id  TEXT    NOT NULL,

    PRIMARY KEY (league_id, draft_year, original_team_id, round),
    FOREIGN KEY (league_id)        REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (original_team_id) REFERENCES teams(id),
    FOREIGN KEY (current_owner_id) REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS team_rotation_pointer (
    team_id    TEXT    NOT NULL,
    season_id  TEXT    NOT NULL,
    series_id  TEXT    NOT NULL DEFAULT '',
    next_order INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT    NOT NULL DEFAULT (NOW()),

    PRIMARY KEY (team_id, season_id, series_id),
    -- series_id = '' is the season pointer, used for regular season and playoffs
    
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- ── GM / Identity layer ───────────────────────────────────────────────────────
--
-- gm_personas: the site-wide library of AI GM personas (src/league/personas.py).
--   A persona never changes once created; only its chance of being picked for
--   a new league (0 never, 100 twice as likely as 50) can. Seeded by
--   migration 026.
CREATE TABLE IF NOT EXISTS gm_personas (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    bio        TEXT NOT NULL DEFAULT '',
    archetype  TEXT NOT NULL DEFAULT '',
    dials      JSONB NOT NULL,
    chance     INTEGER NOT NULL DEFAULT 50 CHECK (chance BETWEEN 0 AND 100),
    created_at TEXT NOT NULL DEFAULT (NOW()),
    updated_at TEXT NOT NULL DEFAULT (NOW())
);

--
-- gms: one row per user per league (plus one per AI slot).
--   user_id is NULL for AI GMs.
--   All league-specific state (team, performance, fired status) lives here.
--   The API resolves identity as: session_token → user → gms WHERE league_id = ?
CREATE TABLE IF NOT EXISTS gms (
    id             TEXT PRIMARY KEY,
    league_id      TEXT NOT NULL,
    user_id        TEXT,                  -- NULL for AI GMs
    team_id        TEXT,                  -- NULL until assigned
    display_name   TEXT NOT NULL,         -- can differ from users.display_name per league
    is_ai          BOOLEAN NOT NULL DEFAULT FALSE,
    is_away        BOOLEAN NOT NULL DEFAULT FALSE,
    career_seasons INTEGER NOT NULL DEFAULT 0,
    warned_at      TEXT,                  -- ISO datetime of performance warning
    fired_at       TEXT,                  -- ISO datetime of firing; NULL = active
    ready_period   INTEGER,               -- ready when = leagues.sim_period
    persona_id     TEXT,                  -- AI GMs: who they are (gm_personas)
    welcomed_at    TIMESTAMPTZ,           -- saw the welcome screen (once per league)
    roster_saved_at TIMESTAMPTZ,          -- first roster save; ends the getting-started bar
    lobby_city     TEXT,                  -- lobby: the team they'll run, by name (migration 042)
    lobby_mascot   TEXT,
    created_at     TEXT NOT NULL DEFAULT (NOW()),

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (persona_id) REFERENCES gm_personas(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE SET NULL,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE SET NULL
);

-- News for one GM, e.g. a player on their team got hurt during a sim, or the
-- game moved a player to keep the roster legal (roster). Kept
-- per GM so everyone sees their own news, whoever ran the sim.
CREATE TABLE IF NOT EXISTS gm_notifications (
    id         SERIAL PRIMARY KEY,
    gm_id      TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('injury', 'returned', 'roster', 'trade')),
    payload    JSONB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (NOW()),
    seen_at    TEXT,                  -- NULL until shown to the GM

    FOREIGN KEY (gm_id) REFERENCES gms(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gm_notifications_unseen
    ON gm_notifications(gm_id) WHERE seen_at IS NULL;

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

CREATE TABLE IF NOT EXISTS pitcher_state (
    player_id            TEXT NOT NULL,
    league_id            TEXT NOT NULL,
    current_energy       REAL NOT NULL CHECK (current_energy >= 0.0 AND current_energy <= 1.0),
    max_energy           REAL NOT NULL DEFAULT 1.0 CHECK (max_energy >= 0.0 AND max_energy <= 1.0),
    consecutive_days     INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_days >= 0),
    last_game_date       TEXT,
    last_pitch_count     INTEGER CHECK (last_pitch_count >= 0),

    PRIMARY KEY (player_id, league_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_energy (
    player_id            TEXT NOT NULL,
    league_id            TEXT NOT NULL,
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
    league_id               TEXT NOT NULL,
    games_remaining         INTEGER NOT NULL DEFAULT 0,  -- legacy: length of injury in days
    return_date             TEXT,                        -- ISO date the player is available again
    PRIMARY KEY (player_id, league_id),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_injury_log (
    id              SERIAL PRIMARY KEY,
    player_id       TEXT NOT NULL,
    season_id       TEXT,                   -- nullable for pre-season injuries
    team_id         TEXT,                   -- the team the player was on when hurt
    injury_date     TEXT NOT NULL,
    severity        TEXT NOT NULL,
    activity        TEXT,
    games_missed    INTEGER NOT NULL,       -- days missed (games, before migration 2)
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id       TEXT    NOT NULL,
    season_id       TEXT    NOT NULL,
    team_id         TEXT    NOT NULL,
    is_postseason   BOOLEAN NOT NULL DEFAULT FALSE,
 
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
    bat_strike_outs_looking INTEGER NOT NULL DEFAULT 0,
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
    pitch_no_hitters    INTEGER NOT NULL DEFAULT 0,
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
    pitch_strike_outs_looking INTEGER NOT NULL DEFAULT 0,
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
    field_double_plays      INTEGER NOT NULL DEFAULT 0,
    field_triple_plays      INTEGER NOT NULL DEFAULT 0,
 
    PRIMARY KEY (player_id, season_id, team_id, is_postseason),
 
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE
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

-- Fractional part of each skill (-0.5 to 0.5) so aging keeps sub-point progress
CREATE TABLE IF NOT EXISTS player_skill_fractions (
    player_id    TEXT PRIMARY KEY,

    clutch       REAL NOT NULL DEFAULT 0,
    speed        REAL NOT NULL DEFAULT 0,
    durability   REAL NOT NULL DEFAULT 0,
    power        REAL NOT NULL DEFAULT 0,
    eye          REAL NOT NULL DEFAULT 0,
    contact      REAL NOT NULL DEFAULT 0,
    base_running REAL NOT NULL DEFAULT 0,
    bunting      REAL NOT NULL DEFAULT 0,
    catching     REAL NOT NULL DEFAULT 0,
    infield      REAL NOT NULL DEFAULT 0,
    outfield     REAL NOT NULL DEFAULT 0,
    arm          REAL NOT NULL DEFAULT 0,
    accuracy     REAL NOT NULL DEFAULT 0,
    stamina      REAL NOT NULL DEFAULT 0,
    recovery     REAL NOT NULL DEFAULT 0,
    ground_balls REAL NOT NULL DEFAULT 0,
    strikes      REAL NOT NULL DEFAULT 0,

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_status (
    player_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN (
        'unassigned', '26man', '40man', 'minors', 'free_agent', 'prospect', 'retired'
    )),
    since TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS team_players (
    team_id   TEXT NOT NULL,
    player_id TEXT NOT NULL,

    PRIMARY KEY (team_id, player_id),

    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS draft_order (
    draft_id      TEXT    NOT NULL,
    team_id       TEXT    NOT NULL,
    pick_position INTEGER NOT NULL,   -- 1-based; 1 = picks first in round 1

    PRIMARY KEY (draft_id, team_id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id)  REFERENCES teams(id)
);

CREATE TABLE IF NOT EXISTS league_season_teams (
    league_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    
    PRIMARY KEY (league_id, season_id, team_id),
    
    FOREIGN KEY (league_id, season_id) REFERENCES league_seasons(league_id, season_id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);

-- Which league ("conference", since leagues holds whole leagues) and
-- division each team plays in (src/league/divisions.py). Set when a league
-- starts; leagues started before divisions existed have no rows.
CREATE TABLE IF NOT EXISTS team_divisions (
    league_id        TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    team_id          TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    conference       TEXT NOT NULL,
    division         TEXT NOT NULL,
    conference_order INTEGER NOT NULL,
    division_order   INTEGER NOT NULL,
    PRIMARY KEY (league_id, team_id)
);
CREATE INDEX IF NOT EXISTS idx_team_divisions_team ON team_divisions(team_id);

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
    line_score JSONB,                 -- runs by inning, away and home
    winner_id TEXT,
    created_at TEXT DEFAULT (NOW()),
    updated_at TEXT,

    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE SET NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (away_team_id) REFERENCES teams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS draft_picks (
    id          SERIAL PRIMARY KEY,
    draft_id    TEXT    NOT NULL,
    pick_number INTEGER NOT NULL,   -- 1-based absolute pick across all rounds
    round       INTEGER NOT NULL,
    gm_id       TEXT    NOT NULL,
    team_id     TEXT    NOT NULL,
    player_id   TEXT    NOT NULL,
    auto_picked BOOLEAN NOT NULL DEFAULT FALSE,
    picked_at   TEXT NOT NULL DEFAULT (NOW()),

    UNIQUE (draft_id, pick_number),
    UNIQUE (draft_id, player_id),   -- each player picked at most once

    FOREIGN KEY (draft_id)  REFERENCES drafts(id)  ON DELETE CASCADE,
    FOREIGN KEY (gm_id)     REFERENCES gms(id),
    FOREIGN KEY (team_id)   REFERENCES teams(id),
    FOREIGN KEY (player_id) REFERENCES players(id)
);

-- draft_strategies: a GM's need chips, age preference and pinned players for
--   one draft (src/league/offseason/draft_strategy.py, migration 018).
CREATE TABLE IF NOT EXISTS draft_strategies (
    gm_id      TEXT   NOT NULL,
    draft_id   TEXT   NOT NULL,
    chips      JSONB  NOT NULL DEFAULT '{{}}',  -- chip key -> level 0-2 (Low, Med, High)
    age_pref   REAL   NOT NULL DEFAULT 0,      -- -1 upside .. 1 ready sooner
    pins       TEXT[] NOT NULL DEFAULT '{{}}',  -- player_ids, in order
    updated_at TEXT   NOT NULL DEFAULT (NOW()),

    PRIMARY KEY (gm_id, draft_id),

    FOREIGN KEY (gm_id)    REFERENCES gms(id)    ON DELETE CASCADE,
    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
);

-- Trades. One row per offer from one team to another (see
-- src/api/services/trades.py). created_on is the league date it was made,
-- which the AI uses so the same offer gets the same answer all day.
CREATE TABLE IF NOT EXISTS trade_offers (
    id           TEXT PRIMARY KEY,
    league_id    TEXT NOT NULL,
    season_id    TEXT NOT NULL,
    from_team_id TEXT NOT NULL,
    to_team_id   TEXT NOT NULL,
    from_gm_id   TEXT,
    parent_id    TEXT,              -- the offer this one counters
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                     'pending', 'pending_vote', 'accepted', 'rejected',
                     'countered', 'withdrawn', 'expired', 'void', 'voted_down'
                 )),
    reason       TEXT,              -- the answer shown to the proposer
    created_on   TEXT NOT NULL,     -- league date (ISO)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at   TIMESTAMPTZ,
    expires_period INTEGER,         -- an offer to a GM: expires before this period runs
    expires_on   TEXT,              -- single player, an AI team's offer: expires after this date
    from_ai      BOOLEAN NOT NULL DEFAULT FALSE,  -- an AI team made it
    vote_period  INTEGER,           -- pending_vote: the vote closes before this period runs

    FOREIGN KEY (league_id)    REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id)    REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (from_team_id) REFERENCES teams(id)   ON DELETE CASCADE,
    FOREIGN KEY (to_team_id)   REFERENCES teams(id)   ON DELETE CASCADE,
    FOREIGN KEY (from_gm_id)   REFERENCES gms(id)     ON DELETE SET NULL,
    FOREIGN KEY (parent_id)    REFERENCES trade_offers(id) ON DELETE SET NULL
);

-- The players in an offer. from_team_id is the side giving the player up.
CREATE TABLE IF NOT EXISTS trade_offer_items (
    offer_id     TEXT NOT NULL,
    player_id    TEXT NOT NULL,
    from_team_id TEXT NOT NULL,

    PRIMARY KEY (offer_id, player_id),

    FOREIGN KEY (offer_id)     REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id)    REFERENCES players(id)      ON DELETE CASCADE,
    FOREIGN KEY (from_team_id) REFERENCES teams(id)        ON DELETE CASCADE
);

-- The draft picks in an offer (src/league/trades/draft_picks.py): a pick is
-- the original team's pick in a round of a year's draft. from_team_id is the
-- side giving it up.
-- Team states (src/league/team_state.py): where each front office sees its
-- team, worked out at checkpoints through the season. The latest row for a
-- team and season is its state; the rest is history.
CREATE TABLE IF NOT EXISTS team_states (
    id         BIGSERIAL PRIMARY KEY,
    league_id  TEXT NOT NULL,
    season_id  TEXT NOT NULL,
    team_id    TEXT NOT NULL,
    as_of      TEXT NOT NULL,        -- league date of the checkpoint
    state      TEXT NOT NULL CHECK (state IN (
                   'all-in', 'contending', 'retooling',
                   'ramping-up', 'rebuilding', 'aging-out'
               )),
    held       INTEGER NOT NULL DEFAULT 1,  -- checkpoints the state has held
    candidate  TEXT NOT NULL,        -- what the inputs said before stickiness
    inputs     JSONB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (NOW()),

    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trade_offer_picks (
    offer_id         TEXT    NOT NULL,
    draft_year       INTEGER NOT NULL,
    round            INTEGER NOT NULL,
    original_team_id TEXT    NOT NULL,
    from_team_id     TEXT    NOT NULL,

    PRIMARY KEY (offer_id, draft_year, round, original_team_id),

    FOREIGN KEY (offer_id)         REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (original_team_id) REFERENCES teams(id)        ON DELETE CASCADE,
    FOREIGN KEY (from_team_id)     REFERENCES teams(id)        ON DELETE CASCADE
);

-- The league's vote on a trade between two GMs: one row per voter (every
-- other GM in the league, not away, when the vote opened). vote is NULL until
-- they vote, and a missing vote counts as no.
CREATE TABLE IF NOT EXISTS trade_votes (
    offer_id  TEXT NOT NULL,
    gm_id     TEXT NOT NULL,
    vote      BOOLEAN,
    voted_at  TIMESTAMPTZ,

    PRIMARY KEY (offer_id, gm_id),

    FOREIGN KEY (offer_id) REFERENCES trade_offers(id) ON DELETE CASCADE,
    FOREIGN KEY (gm_id)    REFERENCES gms(id)          ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gm_lineup_preferences (
    gm_id        TEXT NOT NULL,
    player_id    TEXT NOT NULL,
    batting_order INTEGER,        -- 1-9, NULL for bench/pitcher
    position     TEXT,            -- defensive position
    is_starter   BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at   TEXT NOT NULL DEFAULT (NOW()),
    -- The opposing starter's hand this lineup is for (Lineup tab toggle)
    vs_hand      TEXT NOT NULL DEFAULT 'R' CHECK (vs_hand IN ('R', 'L')),

    PRIMARY KEY (gm_id, vs_hand, player_id),

    FOREIGN KEY (gm_id)     REFERENCES gms(id)     ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- One row per GM, created on join, mutable between series.
CREATE TABLE IF NOT EXISTS gm_profiles (
    gm_id TEXT PRIMARY KEY,

    -- Batting tendencies
    lineup_style     TEXT NOT NULL DEFAULT 'traditional'
                         CHECK (lineup_style     IN ('traditional', 'analytics', 'speed-first', 'power-first')),
    -- Replaced by baserunning (migration 023); no longer read.
    steal_aggression TEXT NOT NULL DEFAULT 'standard'
                         CHECK (steal_aggression IN ('conservative', 'standard', 'aggressive')),
    baserunning      TEXT NOT NULL DEFAULT 'standard'
                         CHECK (baserunning IN ('very-conservative', 'conservative', 'standard',
                                                'aggressive', 'very-aggressive')),
    rest_days        TEXT NOT NULL DEFAULT 'standard'
                         CHECK (rest_days IN ('iron-man', 'standard', 'rest-often')),
    sac_bunt         TEXT NOT NULL DEFAULT 'situational'
                         CHECK (sac_bunt         IN ('never', 'situational', 'frequent')),

    -- Pitching tendencies
    starter_usage TEXT NOT NULL DEFAULT 'pitch-count-strict'
                      CHECK (starter_usage IN ('let-them-work', 'pitch-count-strict', 'matchup-based')),
    closer_usage  TEXT NOT NULL DEFAULT 'saves-only'
                      CHECK (closer_usage  IN ('saves-only', 'high-leverage', 'best-available')),
    bullpen_pref  TEXT NOT NULL DEFAULT 'deep-pen'
                      CHECK (bullpen_pref  IN ('deep-pen', 'starter-heavy')),

    -- Rotation
    rotation_size      INTEGER NOT NULL DEFAULT 5 CHECK (rotation_size IN (4, 5, 6)),
    skip_fifth_starter BOOLEAN NOT NULL DEFAULT FALSE,
    playoff_rotation   TEXT    NOT NULL DEFAULT 'same'
                           CHECK (playoff_rotation IN ('3', '4', 'same')),
    tired_starters     TEXT    NOT NULL DEFAULT 'standard'
                           CHECK (tired_starters IN ('push', 'standard', 'protect')),

    -- Roster tendencies
    platoon_usage TEXT NOT NULL DEFAULT 'vs-handedness'
                      CHECK (platoon_usage IN ('none', 'vs-handedness', 'aggressive')),
    -- How much a player's season stats count against his ratings, 0-100.
    stats_vs_scouting INTEGER NOT NULL DEFAULT 50
                          CHECK (stats_vs_scouting BETWEEN 0 AND 100),

    updated_at TEXT NOT NULL DEFAULT (NOW()),

    FOREIGN KEY (gm_id) REFERENCES gms(id) ON DELETE CASCADE
);

-- gm_career_seasons: one row per person per league season, for the profile
--   page (/gms/USERNAME, src/api/services/career.py). Kept up to date
--   after every sim job, and final once the season is over or the person
--   leaves. No foreign keys to the league, team or season, so it outlives a
--   league that's deleted; names are copied in for the same reason.
CREATE TABLE IF NOT EXISTS gm_career_seasons (
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    league_id      TEXT NOT NULL,
    season_id      TEXT NOT NULL,
    league_name    TEXT NOT NULL,
    season_year    INTEGER NOT NULL,
    team_city      TEXT NOT NULL,
    team_mascot    TEXT NOT NULL,
    wins           INTEGER NOT NULL DEFAULT 0,
    losses         INTEGER NOT NULL DEFAULT 0,      -- regular season
    division_title BOOLEAN NOT NULL DEFAULT FALSE,
    finish         INTEGER,                         -- place in the division (or league
    finish_of      INTEGER,                         --   without divisions), of how many
    playoff_result TEXT CHECK (playoff_result IN
                       ('Round 1', 'Semifinals', 'Finals', 'Champion')),  -- how far they got
    sweeps         INTEGER NOT NULL DEFAULT 0,      -- playoff series won without a loss
    trades         INTEGER NOT NULL DEFAULT 0,      -- accepted trades
    front_office   TEXT,                            -- the team's last team_states state that season
    final          BOOLEAN NOT NULL DEFAULT FALSE,  -- season over, or they left
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, league_id, season_id)
);

-- gm_head_to_head: each person's record against another person, per league
--   season, for the profile's Rivals section. Written from both sides, kept
--   like gm_career_seasons (no foreign keys to the league), and final once
--   the season is over or either of them leaves. Regular season and playoff
--   games both count; series_round is the playoff round they met in.
CREATE TABLE IF NOT EXISTS gm_head_to_head (
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opponent_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    league_id       TEXT NOT NULL,
    season_id       TEXT NOT NULL,
    league_name     TEXT NOT NULL,
    season_year     INTEGER NOT NULL,
    team_city       TEXT NOT NULL,
    team_mascot     TEXT NOT NULL,
    opponent_city   TEXT NOT NULL,
    opponent_mascot TEXT NOT NULL,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    series_round    TEXT,
    series_won      BOOLEAN,
    final           BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, opponent_id, league_id, season_id)
);

-- gm_badges: achievements on the profile page (src/api/services/badges.py).
--   Kept once earned, even if what earned it is later deleted. detail says
--   where, e.g. "Weekend League · 2031".
CREATE TABLE IF NOT EXISTS gm_badges (
    user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge     TEXT NOT NULL,
    detail    TEXT,
    earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, badge)
);

-- Written at season end by the evaluation job.
CREATE TABLE IF NOT EXISTS gm_season_evaluations (
    gm_id                 TEXT NOT NULL,
    season_id             TEXT NOT NULL,
    wins                  INTEGER NOT NULL DEFAULT 0,
    losses                INTEGER NOT NULL DEFAULT 0,
    expected_wins         REAL,
    roster_quality_rating REAL,
    made_playoffs         BOOLEAN NOT NULL DEFAULT FALSE,
    won_championship      BOOLEAN NOT NULL DEFAULT FALSE,
    verdict               TEXT CHECK (verdict IN ('retained', 'warned', 'fired')),
    evaluated_at          TEXT NOT NULL DEFAULT (NOW()),

    PRIMARY KEY (gm_id, season_id),

    FOREIGN KEY (gm_id)     REFERENCES gms(id)     ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS game_events (
    id            SERIAL PRIMARY KEY,
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
    created_at    TEXT NOT NULL DEFAULT (NOW()),
 
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
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
    double_plays          INTEGER DEFAULT 0 CHECK (double_plays >= 0),
    triple_plays          INTEGER DEFAULT 0 CHECK (triple_plays >= 0),

    PRIMARY KEY (game_id, player_id, position),

    FOREIGN KEY (game_id)   REFERENCES games(id)   ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- 1 row per player per game
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
    bat_strike_outs_looking INTEGER DEFAULT 0 CHECK (bat_strike_outs_looking >= 0),
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
    pitch_no_hitter INTEGER DEFAULT 0 CHECK (pitch_no_hitter IN (0, 1)),
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
    pitch_strike_outs_looking INTEGER DEFAULT 0 CHECK (pitch_strike_outs_looking >= 0),
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
    field_double_plays INTEGER DEFAULT 0 CHECK (field_double_plays >= 0),
    field_triple_plays INTEGER DEFAULT 0 CHECK (field_triple_plays >= 0),

    PRIMARY KEY (game_id, player_id),
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
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

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_draft_order_draft ON draft_order(draft_id);

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

CREATE TABLE IF NOT EXISTS player_retirements (
    id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    player_id      TEXT NOT NULL,
    league_id      TEXT NOT NULL,
    season_id      TEXT NOT NULL,
    former_team_id TEXT,
    retired_at     TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
    FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
);

-- All-Star voting (plans/all-star-game.md). A team's ballot: pick 1 and 2 at
-- each fielding position (slot c, 1b, ... rf), pick 1 at dh, picks 1-9 at p.
CREATE TABLE IF NOT EXISTS all_star_votes (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    slot       TEXT NOT NULL,
    pick       INTEGER NOT NULL,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    PRIMARY KEY (season_id, team_id, slot, pick)
);

-- The players voted in, with the team they were on and the slot they were
-- voted at. wildcard: in on total points rather than his position's quota.
CREATE TABLE IF NOT EXISTS all_stars (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    slot       TEXT NOT NULL,
    points     INTEGER NOT NULL DEFAULT 0,
    wildcard   BOOLEAN NOT NULL DEFAULT FALSE,
    score      REAL NOT NULL DEFAULT 0,   -- stat score at the vote (draft order)
    replaces   TEXT REFERENCES players(id) ON DELETE SET NULL,  -- a reserve: the injured All-Star
    PRIMARY KEY (season_id, player_id)
);

-- The All-Star Game. Captain 1 (best record at the break) picks first and is
-- the home side. state: 'tie' while captain 2 picks the last wildcard from
-- tied_ids, 'draft' while the captains pick, 'played' once it's over.
-- Scores are by side; line_score is {{"1": [...], "2": [...]}} runs by inning.
CREATE TABLE IF NOT EXISTS all_star_games (
    season_id    TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
    captain1_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    captain2_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    state        TEXT NOT NULL DEFAULT 'draft'
                     CHECK (state IN ('tie', 'draft', 'played')),
    tied_ids     TEXT[] NOT NULL DEFAULT '{{}}',
    auto1        BOOLEAN NOT NULL DEFAULT FALSE,
    auto2        BOOLEAN NOT NULL DEFAULT FALSE,
    game_date    TEXT,
    score1       INTEGER,
    score2       INTEGER,
    innings      INTEGER,
    line_score   JSONB,
    mvp_player_id TEXT REFERENCES players(id) ON DELETE SET NULL
);

-- The captains' draft: which side took each All-Star, in pick order.
CREATE TABLE IF NOT EXISTS all_star_picks (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    side       INTEGER NOT NULL CHECK (side IN (1, 2)),
    pick       INTEGER NOT NULL,
    PRIMARY KEY (season_id, player_id),
    UNIQUE (season_id, pick)
);

-- Each player's line in the All-Star Game, apart from the season's stats.
CREATE TABLE IF NOT EXISTS all_star_game_stats (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    side       INTEGER NOT NULL CHECK (side IN (1, 2)),
    position   TEXT,
    batting_order INTEGER,
    bat_ab     INTEGER NOT NULL DEFAULT 0,
    bat_runs   INTEGER NOT NULL DEFAULT 0,
    bat_hits   INTEGER NOT NULL DEFAULT 0,
    bat_doubles INTEGER NOT NULL DEFAULT 0,
    bat_triples INTEGER NOT NULL DEFAULT 0,
    bat_home_runs INTEGER NOT NULL DEFAULT 0,
    bat_rbi    INTEGER NOT NULL DEFAULT 0,
    bat_walks  INTEGER NOT NULL DEFAULT 0,
    bat_strike_outs INTEGER NOT NULL DEFAULT 0,
    bat_stolen_bases INTEGER NOT NULL DEFAULT 0,
    pitch_order INTEGER,
    pitch_outs INTEGER NOT NULL DEFAULT 0,
    pitch_hits INTEGER NOT NULL DEFAULT 0,
    pitch_runs INTEGER NOT NULL DEFAULT 0,
    pitch_earned_runs INTEGER NOT NULL DEFAULT 0,
    pitch_walks INTEGER NOT NULL DEFAULT 0,
    pitch_strike_outs INTEGER NOT NULL DEFAULT 0,
    pitch_home_runs INTEGER NOT NULL DEFAULT 0,
    pitch_win  BOOLEAN NOT NULL DEFAULT FALSE,
    pitch_loss BOOLEAN NOT NULL DEFAULT FALSE,
    pitch_save BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (season_id, player_id)
);

-- The Rookie Game: the season's best rookies who aren't All-Stars, picked by
-- the stats when the All-Star votes are counted, and the game, its draft and
-- its lines. Laid out like the All-Star Game's tables, so the same code runs
-- both (AllStarRepository with event="rookie").
CREATE TABLE IF NOT EXISTS rookie_game_players (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    slot       TEXT NOT NULL,
    points     INTEGER NOT NULL DEFAULT 0,
    wildcard   BOOLEAN NOT NULL DEFAULT FALSE,
    score      REAL NOT NULL DEFAULT 0,
    replaces   TEXT REFERENCES players(id) ON DELETE SET NULL,
    PRIMARY KEY (season_id, player_id)
);

CREATE TABLE IF NOT EXISTS rookie_games (
    season_id    TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
    captain1_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    captain2_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    state        TEXT NOT NULL DEFAULT 'draft'
                     CHECK (state IN ('tie', 'draft', 'played')),
    tied_ids     TEXT[] NOT NULL DEFAULT '{{}}',
    auto1        BOOLEAN NOT NULL DEFAULT FALSE,
    auto2        BOOLEAN NOT NULL DEFAULT FALSE,
    game_date    TEXT,
    score1       INTEGER,
    score2       INTEGER,
    innings      INTEGER,
    line_score   JSONB,
    mvp_player_id TEXT REFERENCES players(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS rookie_game_picks (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    side       INTEGER NOT NULL CHECK (side IN (1, 2)),
    pick       INTEGER NOT NULL,
    PRIMARY KEY (season_id, player_id),
    UNIQUE (season_id, pick)
);

CREATE TABLE IF NOT EXISTS rookie_game_stats (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    side       INTEGER NOT NULL CHECK (side IN (1, 2)),
    position   TEXT,
    batting_order INTEGER,
    bat_ab     INTEGER NOT NULL DEFAULT 0,
    bat_runs   INTEGER NOT NULL DEFAULT 0,
    bat_hits   INTEGER NOT NULL DEFAULT 0,
    bat_doubles INTEGER NOT NULL DEFAULT 0,
    bat_triples INTEGER NOT NULL DEFAULT 0,
    bat_home_runs INTEGER NOT NULL DEFAULT 0,
    bat_rbi    INTEGER NOT NULL DEFAULT 0,
    bat_walks  INTEGER NOT NULL DEFAULT 0,
    bat_strike_outs INTEGER NOT NULL DEFAULT 0,
    bat_stolen_bases INTEGER NOT NULL DEFAULT 0,
    pitch_order INTEGER,
    pitch_outs INTEGER NOT NULL DEFAULT 0,
    pitch_hits INTEGER NOT NULL DEFAULT 0,
    pitch_runs INTEGER NOT NULL DEFAULT 0,
    pitch_earned_runs INTEGER NOT NULL DEFAULT 0,
    pitch_walks INTEGER NOT NULL DEFAULT 0,
    pitch_strike_outs INTEGER NOT NULL DEFAULT 0,
    pitch_home_runs INTEGER NOT NULL DEFAULT 0,
    pitch_win  BOOLEAN NOT NULL DEFAULT FALSE,
    pitch_loss BOOLEAN NOT NULL DEFAULT FALSE,
    pitch_save BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (season_id, player_id)
);

-- The Home Run Derby: each hitter's line in each matchup. Round 1 is the
-- field (seeded by home runs); the last round's winner is the champion.
CREATE TABLE IF NOT EXISTS hr_derby_results (
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    round      INTEGER NOT NULL,
    match      INTEGER NOT NULL,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id    TEXT REFERENCES teams(id) ON DELETE SET NULL,
    seed       INTEGER NOT NULL,
    homers     INTEGER NOT NULL DEFAULT 0,
    swingoff   INTEGER,                   -- home runs in swing-offs, if tied
    longest    INTEGER NOT NULL DEFAULT 0,  -- feet
    won        BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (season_id, round, player_id)
);

CREATE INDEX IF NOT EXISTS idx_all_star_votes_team   ON all_star_votes(team_id);
CREATE INDEX IF NOT EXISTS idx_all_star_votes_player ON all_star_votes(player_id);
CREATE INDEX IF NOT EXISTS idx_all_stars_player      ON all_stars(player_id);
CREATE INDEX IF NOT EXISTS idx_all_stars_team        ON all_stars(team_id);
CREATE INDEX IF NOT EXISTS idx_hr_derby_results_player ON hr_derby_results(player_id);
CREATE INDEX IF NOT EXISTS idx_hr_derby_results_team   ON hr_derby_results(team_id);
-- idx_all_stars_replaces is made by migration 036, which adds the column to
-- databases from before it: this runs first, before the column is there.
CREATE INDEX IF NOT EXISTS idx_all_star_games_c1     ON all_star_games(captain1_team_id);
CREATE INDEX IF NOT EXISTS idx_all_star_games_c2     ON all_star_games(captain2_team_id);
CREATE INDEX IF NOT EXISTS idx_all_star_games_mvp    ON all_star_games(mvp_player_id);
CREATE INDEX IF NOT EXISTS idx_all_star_picks_player ON all_star_picks(player_id);
CREATE INDEX IF NOT EXISTS idx_all_star_game_stats_player ON all_star_game_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_game_players_player ON rookie_game_players(player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_game_players_team ON rookie_game_players(team_id);
CREATE INDEX IF NOT EXISTS idx_rookie_game_players_replaces ON rookie_game_players(replaces);
CREATE INDEX IF NOT EXISTS idx_rookie_games_c1 ON rookie_games(captain1_team_id);
CREATE INDEX IF NOT EXISTS idx_rookie_games_c2 ON rookie_games(captain2_team_id);
CREATE INDEX IF NOT EXISTS idx_rookie_games_mvp ON rookie_games(mvp_player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_game_picks_player ON rookie_game_picks(player_id);
CREATE INDEX IF NOT EXISTS idx_rookie_game_stats_player ON rookie_game_stats(player_id);

CREATE INDEX IF NOT EXISTS idx_player_retirements_league_season
    ON player_retirements(league_id, season_id);

CREATE INDEX IF NOT EXISTS idx_users_session        ON users(session_token);

CREATE INDEX IF NOT EXISTS idx_gms_league           ON gms(league_id);

CREATE INDEX IF NOT EXISTS idx_gms_user             ON gms(user_id);

CREATE INDEX IF NOT EXISTS idx_gms_team             ON gms(team_id);

-- idx_gms_persona (gms.persona_id) is made by migration 026: on a database
-- from before it, gms has no persona_id yet when this file runs.

CREATE INDEX IF NOT EXISTS idx_leagues_join_code    ON leagues(join_code);

CREATE INDEX IF NOT EXISTS idx_drafts_league_season ON drafts(league_id, season_id);

CREATE INDEX IF NOT EXISTS idx_draft_picks_draft    ON draft_picks(draft_id);

CREATE INDEX IF NOT EXISTS idx_draft_picks_gm       ON draft_picks(gm_id);

CREATE INDEX IF NOT EXISTS idx_draft_picks_player   ON draft_picks(player_id);

CREATE INDEX IF NOT EXISTS idx_gm_evals_season      ON gm_season_evaluations(season_id);
CREATE INDEX IF NOT EXISTS idx_gm_h2h_opponent       ON gm_head_to_head(opponent_id);

CREATE INDEX IF NOT EXISTS idx_lineup_pref_gm       ON gm_lineup_preferences(gm_id);

CREATE INDEX IF NOT EXISTS idx_players_league       ON players(league_id);

CREATE INDEX IF NOT EXISTS idx_game_events_game
    ON game_events(game_id);

CREATE INDEX IF NOT EXISTS idx_game_events_type
    ON game_events(game_id, event_type);

CREATE INDEX IF NOT EXISTS idx_game_events_player
    ON game_events(player_id);

CREATE INDEX IF NOT EXISTS idx_pick_rights_league_year
    ON draft_pick_rights(league_id, draft_year);

CREATE INDEX IF NOT EXISTS idx_pick_rights_owner
    ON draft_pick_rights(current_owner_id);

CREATE INDEX IF NOT EXISTS idx_trade_offers_league
    ON trade_offers(league_id, season_id);

CREATE INDEX IF NOT EXISTS idx_trade_offer_items_player
    ON trade_offer_items(player_id);

CREATE INDEX IF NOT EXISTS idx_trade_offers_season    ON trade_offers(season_id);
CREATE INDEX IF NOT EXISTS idx_trade_offers_from_team ON trade_offers(from_team_id);
CREATE INDEX IF NOT EXISTS idx_trade_offers_to_team   ON trade_offers(to_team_id);
CREATE INDEX IF NOT EXISTS idx_trade_offers_from_gm   ON trade_offers(from_gm_id);
CREATE INDEX IF NOT EXISTS idx_trade_offer_items_team ON trade_offer_items(from_team_id);
CREATE INDEX IF NOT EXISTS idx_trade_offer_picks_original
    ON trade_offer_picks(original_team_id);
CREATE INDEX IF NOT EXISTS idx_trade_offer_picks_team ON trade_offer_picks(from_team_id);
CREATE INDEX IF NOT EXISTS idx_team_states_team
    ON team_states(team_id, season_id, id);
CREATE INDEX IF NOT EXISTS idx_team_states_league
    ON team_states(league_id, season_id);
CREATE INDEX IF NOT EXISTS idx_team_states_season ON team_states(season_id);
CREATE INDEX IF NOT EXISTS idx_trade_votes_gm         ON trade_votes(gm_id);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);

CREATE INDEX IF NOT EXISTS idx_login_failures_username ON login_failures(username, created_at);
CREATE INDEX IF NOT EXISTS idx_login_failures_ip ON login_failures(ip, created_at);
CREATE INDEX IF NOT EXISTS idx_password_resets_ip ON password_resets(requested_ip, created_at);

-- One per foreign key that no other index starts with. Deleting a row checks
-- every table that references it, and without an index each check scans the
-- whole table: deleting a league's ~1,400 players scanned the per-game tables
-- once per player, so leaving a league took minutes once others had history.
CREATE INDEX IF NOT EXISTS idx_lineup_slots_player     ON game_lineup_slots(player_id);
CREATE INDEX IF NOT EXISTS idx_game_fielding_player    ON player_game_fielding(player_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_team  ON player_game_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_games_series            ON games(series_id);
CREATE INDEX IF NOT EXISTS idx_series_season           ON series(season_id);
CREATE INDEX IF NOT EXISTS idx_bullpen_roles_season    ON bullpen_roles(season_id);
CREATE INDEX IF NOT EXISTS idx_team_rotations_player   ON team_rotations(player_id);
CREATE INDEX IF NOT EXISTS idx_team_rotations_season   ON team_rotations(season_id);
CREATE INDEX IF NOT EXISTS idx_rotation_pointer_season ON team_rotation_pointer(season_id);
CREATE INDEX IF NOT EXISTS idx_drafts_season           ON drafts(season_id);
CREATE INDEX IF NOT EXISTS idx_draft_order_team        ON draft_order(team_id);
CREATE INDEX IF NOT EXISTS idx_draft_picks_team        ON draft_picks(team_id);
CREATE INDEX IF NOT EXISTS idx_pick_rights_original    ON draft_pick_rights(original_team_id);
CREATE INDEX IF NOT EXISTS idx_draft_strategies_draft ON draft_strategies(draft_id);
CREATE INDEX IF NOT EXISTS idx_lineup_pref_player      ON gm_lineup_preferences(player_id);
CREATE INDEX IF NOT EXISTS idx_league_seasons_season   ON league_seasons(season_id);
CREATE INDEX IF NOT EXISTS idx_player_retirements_player ON player_retirements(player_id);
CREATE INDEX IF NOT EXISTS idx_player_retirements_season ON player_retirements(season_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sim_jobs_one_active  ON sim_jobs(league_id) WHERE state IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_sim_jobs_queue          ON sim_jobs(run_after) WHERE state = 'queued';

-- Deferred FK: leagues.commissioner_gm_id → gms (circular; added after gms exists)
ALTER TABLE leagues
    DROP CONSTRAINT IF EXISTS leagues_commissioner_gm_id_fkey;
ALTER TABLE leagues
    ADD CONSTRAINT leagues_commissioner_gm_id_fkey
    FOREIGN KEY (commissioner_gm_id) REFERENCES gms(id) ON DELETE SET NULL;
"""
