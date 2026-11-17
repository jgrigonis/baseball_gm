# src/db/migration_files/migration_140_playoff_eligible.py
"""
Long Form's September 1 playoff rule (Josh, 2026-11-16): each team's 40-man
(and 60-day injured list) as it stood on September 1. Only those players
can be on a playoff roster, except as a replacement for an eligible player
who's hurt.
"""

VERSION = 140


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS playoff_eligible (
               league_id TEXT NOT NULL,
               season_id TEXT NOT NULL,
               team_id TEXT NOT NULL,
               player_id TEXT NOT NULL,
               PRIMARY KEY (season_id, team_id, player_id)
           )"""
    )
