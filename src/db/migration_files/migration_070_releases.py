# src/db/migration_files/migration_070_releases.py
"""
Releasing players and signing free agents (src/api/services/free_agents.py).

player_contracts gets three columns:
- guaranteed: the deal is owed in full. It turns on once the player is on the
  40-man (26man or 40man) under it, and for any free agent signing. A minors
  player who has never been on the 40-man can be released for nothing.
- released_year / released_team_id: the season a team released him and which
  team. The deal stops being his from that season on; if it was guaranteed,
  the rest of it stays on that team's payroll as dead money.

A released player can sign a new deal the same season his old one started,
so the one-deal-per-start-year rule now covers only deals still in force.

Backfill: deals of players on a 40-man today are guaranteed.
"""

VERSION = 70


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS"
        " guaranteed BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS released_year INTEGER"
    )
    conn.execute(
        "ALTER TABLE player_contracts ADD COLUMN IF NOT EXISTS released_team_id TEXT"
        " REFERENCES teams(id) ON DELETE SET NULL"
    )
    conn.execute(
        "ALTER TABLE player_contracts"
        " DROP CONSTRAINT IF EXISTS player_contracts_player_id_start_year_key"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_player_contracts_in_force"
        " ON player_contracts(player_id, start_year) WHERE released_year IS NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_contracts_released"
        " ON player_contracts(released_team_id) WHERE released_team_id IS NOT NULL"
    )
    conn.execute(
        """
        UPDATE player_contracts c SET guaranteed = TRUE
        FROM player_status ps
        WHERE ps.player_id = c.player_id AND ps.status IN ('26man', '40man')
        """
    )
