# src/db/migration_files/migration_015_practice_leagues.py
"""
Practice leagues and the new-user tutorial.

A practice league is a solo league with a coach panel that walks a new GM
through their first season. It only shows on its owner's Practice tab, never
in public lists. coach_done holds the coach steps the GM has done that the
league's state can't tell by itself, like saving a lineup.

users.dismissed_tips holds the first-visit tab tips each user has closed.
"""

VERSION = 15


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS is_practice BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS coach_done TEXT[] NOT NULL DEFAULT '{}'"
    )
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS dismissed_tips TEXT[] NOT NULL DEFAULT '{}'"
    )
