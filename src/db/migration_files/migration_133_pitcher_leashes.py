# src/db/migration_files/migration_133_pitcher_leashes.py
"""
Starter Leash per pitcher (Josh, 2026-11-14): a starter can have his own
pitch count, overriding the team's Starter Leash (src/team/manager_profile.py
leash_for). Set on the Lineup tab's rotation rows; keyed by team, so it
lapses when he leaves.
"""

VERSION = 133


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pitcher_leashes (
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    pitches    TEXT NOT NULL CHECK (pitches IN ('75', '85', '95', '105', '115')),
    PRIMARY KEY (team_id, player_id)
)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pitcher_leashes_player"
        " ON pitcher_leashes(player_id)"
    )
