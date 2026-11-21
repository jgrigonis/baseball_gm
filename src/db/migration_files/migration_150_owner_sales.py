# src/db/migration_files/migration_150_owner_sales.py
"""
Owners sell the team when their bank ends a season too far in the red
(Josh, 2026-11-21: "big negative banks should trigger some kind of event";
src/api/services/owner_sales.py). owner_sales remembers each sale: the old
owner's bank start and season, the debt they left, and the buyer's bank.
"""

VERSION = 150


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS owner_sales (
               league_id      TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               team_id        TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
               year           INTEGER NOT NULL,
               old_owner_id   TEXT NOT NULL,
               new_owner_id   TEXT NOT NULL,
               old_bank_start BIGINT NOT NULL,
               old_bank_year  INTEGER NOT NULL,
               debt           BIGINT NOT NULL,
               new_bank       BIGINT NOT NULL,
               created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (league_id, team_id, year)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_owner_sales_team ON owner_sales(team_id)"
    )
