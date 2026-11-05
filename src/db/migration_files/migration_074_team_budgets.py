# src/db/migration_files/migration_074_team_budgets.py
"""
Team budgets (src/league/budget.py): the payroll each team's owner will pay
for a season, and the luxury tax on payroll over it. Rows are made the first
time a league's budgets are needed, so existing leagues need nothing more.
"""

VERSION = 74


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_budgets (
            league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            year        INTEGER NOT NULL,
            budget      BIGINT NOT NULL,
            luxury_tax  BIGINT,
            PRIMARY KEY (league_id, team_id, year)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_budgets_team ON team_budgets(team_id)"
    )
