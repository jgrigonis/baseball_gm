"""
Broadcast deals and merchandise (Josh, 2026-11-09): two more lines of team
revenue (src/league/finances.py). broadcast_deals holds each team's local TV
deals, the price locked when one is signed; team_budgets records what each
finished season earned from its deal and its merchandise.
"""

VERSION = 100


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS broadcast_deals (
               league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
               start_year INTEGER NOT NULL,
               years      SMALLINT NOT NULL CHECK (years >= 1),
               base       BIGINT NOT NULL,
               fans       INTEGER NOT NULL,
               win_pct    REAL NOT NULL,
               PRIMARY KEY (league_id, team_id, start_year)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_broadcast_deals_team ON broadcast_deals(team_id)"
    )
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS broadcast_revenue BIGINT"
    )
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS merch_revenue BIGINT"
    )
