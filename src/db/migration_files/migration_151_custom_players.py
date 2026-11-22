# src/db/migration_files/migration_151_custom_players.py
"""
Made-up players (Josh, 2026-11-22): a contributor makes their own players
(src/api/services/custom_players.py) and puts them on custom teams next to
real player-seasons. custom_players holds each one: name, position, age,
handedness, skills, talent ceilings, personality, face, home region and
jersey wishes. A custom team names one as {"made": "<id>"} in its players
list; a league gets a copy of him when the team goes in.

Two things that were only ever drawn from a player's id can now be stored,
so a made-up player keeps what was picked for him:
- players.face: his face traits (src/player/face.py). NULL = the random face
  from his id, as before.
- player_personality.ruiner: morale ruiner. NULL = drawn from his id, as
  before.
"""

VERSION = 151

TABLE = """
CREATE TABLE IF NOT EXISTS custom_players (
    id           TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    position     TEXT NOT NULL,
    bats         TEXT NOT NULL,
    throws       TEXT NOT NULL,
    age          INTEGER NOT NULL,
    skills       JSONB NOT NULL,
    caps         JSONB NOT NULL,
    personality  JSONB NOT NULL,
    face         JSONB NOT NULL,
    home_region  TEXT NOT NULL,
    jersey_prefs TEXT[] NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def upgrade(conn):
    conn.execute(TABLE)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_custom_players_owner ON custom_players(owner_id)"
    )
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS face JSONB")
    conn.execute(
        "ALTER TABLE player_personality ADD COLUMN IF NOT EXISTS ruiner BOOLEAN"
    )
