# src/db/migration_files/migration_144_lobby_owners.py
"""
Owners in the lobby (Josh, 2026-11-19): each lobby team is drawn its owner
before the league starts, so people see who they'd work for while picking a
team. league_lobby_teams.owner_id holds the draw
(src/api/services/owners.py lobby_owners); the start seats the same owner
(owners.ensure). A team swapped in from the pool gets a fresh draw. No
foreign key, so a deleted library owner just gets redrawn.
"""

VERSION = 144


def upgrade(conn):
    conn.execute(
        "ALTER TABLE league_lobby_teams ADD COLUMN IF NOT EXISTS owner_id TEXT"
    )
