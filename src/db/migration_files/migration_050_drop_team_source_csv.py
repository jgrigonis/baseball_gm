# src/db/migration_files/migration_050_drop_team_source_csv.py
"""
Teams no longer come from CSV files: a league's teams are generated and
saved straight to the database when it starts (src/api/services/league_start.py).
So teams.source_csv and teams.source_hash, the file each team was imported
from and its hash, go.
"""

VERSION = 50


def upgrade(conn):
    conn.execute("ALTER TABLE teams DROP COLUMN IF EXISTS source_csv")
    conn.execute("ALTER TABLE teams DROP COLUMN IF EXISTS source_hash")
