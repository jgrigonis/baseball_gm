"""
Ballpark upgrades (Josh, 2026-11-09: stadium upgrades for rich owners,
src/league/finances.py BALLPARK). ballpark_projects holds each team's
projects: what the owner paid from their bank and the season it opened.
team_budgets records what each finished season's ballpark earned.
"""

VERSION = 103


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ballpark_projects (
               league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               team_id   TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
               project   TEXT NOT NULL,
               year      INTEGER NOT NULL,
               cost      BIGINT NOT NULL,
               PRIMARY KEY (league_id, team_id, project)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ballpark_projects_team"
        " ON ballpark_projects(team_id)"
    )
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS ballpark_revenue BIGINT"
    )
