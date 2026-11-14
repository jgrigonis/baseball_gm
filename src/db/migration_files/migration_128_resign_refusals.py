# src/db/migration_files/migration_128_resign_refusals.py
"""
Veterans who won't re-sign at any price (Josh, 2026-11-13: about 1 in 20
expiring veterans, src/player/happiness.py refuses_to_resign). Recorded
when the re-sign window closes so the team he left can't win him back in
bidding or sign him the next season.
"""

VERSION = 128


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS resign_refusals (
    league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    year       INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    PRIMARY KEY (player_id, year)
)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_resign_refusals_league
           ON resign_refusals(league_id)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_resign_refusals_team
           ON resign_refusals(team_id)"""
    )
