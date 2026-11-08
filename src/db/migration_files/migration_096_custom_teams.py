# src/db/migration_files/migration_096_custom_teams.py
"""
Custom teams (Josh, 2026-11-08): a contributor builds a team from real
player-seasons (src/league/real_seasons/players.py), can hand-edit their
skills, and shares it by code. Anyone who opens the code can save a copy of
their own. players is a JSON list of {"key": "griffke02-1997", "skills":
{...} or null}; skills is only set once someone edits them.

A league's commissioner can put one of their custom teams on any team in a
single-player lobby (league_custom_teams, a copy of the players at the
time). leagues.single_player then keeps anyone else from joining, and
gm_career_seasons.custom_teams keeps its seasons from earning GM badges.
"""

VERSION = 96

TABLE = """
CREATE TABLE IF NOT EXISTS custom_teams (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    share_code  TEXT UNIQUE NOT NULL,
    copied_from TEXT,
    players     JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


LEAGUE_TABLE = """
CREATE TABLE IF NOT EXISTS league_custom_teams (
    league_id      TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    city           TEXT NOT NULL,
    mascot         TEXT NOT NULL,
    custom_team_id TEXT,
    name           TEXT NOT NULL,
    players        JSONB NOT NULL,
    PRIMARY KEY (league_id, city, mascot)
)
"""


def upgrade(conn):
    conn.execute(TABLE)
    conn.execute(LEAGUE_TABLE)
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS"
        " single_player BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE gm_career_seasons ADD COLUMN IF NOT EXISTS"
        " custom_teams BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_custom_teams_owner ON custom_teams(owner_id)"
    )
