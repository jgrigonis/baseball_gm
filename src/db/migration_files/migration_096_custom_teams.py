# src/db/migration_files/migration_096_custom_teams.py
"""
Custom teams (Josh, 2026-11-08): a contributor builds a team from real
player-seasons (src/league/real_seasons/players.py), can hand-edit their
skills, and shares it by code. Anyone who opens the code can save a copy of
their own. players is a JSON list of {"key": "griffke02-1997", "skills":
{...} or null}; skills is only set once someone edits them.
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


def upgrade(conn):
    conn.execute(TABLE)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_custom_teams_owner ON custom_teams(owner_id)"
    )
