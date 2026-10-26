# src/db/migration_files/migration_009_public_leagues.py
"""
Whether a league is listed under Public Leagues on the leagues page, where
anyone can find it and join while it's in the lobby.

Existing leagues stay private: they were made expecting only people with
the join code to find them.
"""

VERSION = 9


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE"
    )
