# src/db/migration_files/migration_131_joined_on.py
"""
The league date a player joined his team by trade, signing or claim
(src/api/services/arrivals.py), for the NEW tag on Roster and Lineup.
"""

VERSION = 131


def upgrade(conn):
    conn.execute("ALTER TABLE team_players ADD COLUMN IF NOT EXISTS joined_on TEXT")
