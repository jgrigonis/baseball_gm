# src/db/migration_files/migration_127_payroll_adjustments.py
"""
Salaries split by days for players who change teams during the season
(Josh, 2026-11-13, src/league/prorate.py). Each in-season trade, waiver
claim or free agent signing leaves adjustments to the season's payroll:
the share of a salary for the part of the season a team did (or didn't)
have the player. ContractRepository.payroll adds them up.
"""

VERSION = 127


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS payroll_adjustments (
    id         BIGSERIAL PRIMARY KEY,
    league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    year       INTEGER NOT NULL,
    player_id  TEXT REFERENCES players(id) ON DELETE SET NULL,
    amount     BIGINT NOT NULL,
    reason     TEXT NOT NULL,
    played     REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (NOW())
)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_payroll_adjustments_team
           ON payroll_adjustments(team_id, year)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_payroll_adjustments_league
           ON payroll_adjustments(league_id)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_payroll_adjustments_player
           ON payroll_adjustments(player_id)"""
    )
