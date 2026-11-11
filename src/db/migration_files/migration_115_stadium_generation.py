"""
Replacing a stadium (Josh, 2026-11-11): once a new stadium is 25 seasons
old the owner can build another, of the same tier or higher
(src/league/finances.py STADIUM_LIFE), so a team can build the same project
more than once. generation counts a team's stadiums (1 for the first) and
joins the key.
"""

VERSION = 115


def upgrade(conn):
    conn.execute(
        "ALTER TABLE ballpark_projects"
        " ADD COLUMN IF NOT EXISTS generation SMALLINT NOT NULL DEFAULT 1"
    )
    conn.execute(
        "ALTER TABLE ballpark_projects DROP CONSTRAINT IF EXISTS ballpark_projects_pkey"
    )
    conn.execute(
        "ALTER TABLE ballpark_projects"
        " ADD PRIMARY KEY (league_id, team_id, project, generation)"
    )
