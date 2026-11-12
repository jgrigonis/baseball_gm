# src/db/migration_files/migration_123_record_book.py
"""
The record book (src/api/services/records/, Josh 2026-11-12): single-game
and streak records kept as games are played, how far each season has been
read, the streaks still going, and whether a league has been caught up
(its backstory replayed and its played days read) once.
"""

VERSION = 123


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS records_seeded"
        " BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS record_feats (
    id          BIGSERIAL PRIMARY KEY,
    league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('game', 'streak')),
    stat        TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       INTEGER NOT NULL,
    subject     TEXT NOT NULL,              -- the player, or the club for a club streak
    player_id   TEXT REFERENCES players(id) ON DELETE CASCADE,
    team_id     TEXT,
    season_id   TEXT REFERENCES seasons(id) ON DELETE CASCADE,
    year        INTEGER,
    game_id     TEXT,                       -- the game (a streak's last)
    on_date     TEXT,                       -- the game's date (a streak's last)
    start_date  TEXT,                       -- a streak's first game
    opp_team_id TEXT,
    innings     INTEGER,
    source      TEXT NOT NULL DEFAULT 'played',
    active      BOOLEAN NOT NULL DEFAULT FALSE,  -- a streak still going
    UNIQUE (league_id, key)
)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_record_feats_stat
    ON record_feats(league_id, kind, stat, value DESC)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_record_feats_player_id ON record_feats(player_id)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_record_feats_season_id ON record_feats(season_id)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS record_progress (
    league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    through   TEXT NOT NULL DEFAULT '',
    closed    BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (league_id, season_id)
)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_record_progress_season_id ON record_progress(season_id)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS record_runs (
    league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    stat       TEXT NOT NULL,
    subject    TEXT NOT NULL,
    team_id    TEXT,
    length     INTEGER NOT NULL,
    start_date TEXT,
    last_date  TEXT,
    start_game TEXT,
    last_game  TEXT,
    PRIMARY KEY (league_id, season_id, stat, subject)
)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_record_runs_season_id ON record_runs(season_id)"""
    )
