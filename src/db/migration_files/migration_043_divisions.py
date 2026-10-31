# src/db/migration_files/migration_043_divisions.py
"""
Leagues and divisions (src/league/divisions.py).

- team_divisions: which league ("conference" here, since leagues is the
  table of whole leagues) and division each team plays in. Filled when a
  league starts. Leagues started before this have none.
- leagues.weighted_schedule: play division rivals more often than the rest.
"""

VERSION = 43


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS team_divisions (
               league_id        TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               team_id          TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
               conference       TEXT NOT NULL,
               division         TEXT NOT NULL,
               conference_order INTEGER NOT NULL,
               division_order   INTEGER NOT NULL,
               PRIMARY KEY (league_id, team_id)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_divisions_team ON team_divisions(team_id)"
    )
    conn.execute(
        """ALTER TABLE leagues ADD COLUMN IF NOT EXISTS
               weighted_schedule BOOLEAN NOT NULL DEFAULT FALSE"""
    )
