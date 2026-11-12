# src/db/migration_files/migration_122_fa_talks.py
"""
Making a free agent an offer outside the bidding window (Josh, 2026-11-12;
src/api/services/fa_offers.py). fa_talks holds, for each club and free
agent, the week's offers, the deal he said he'd take, and how long he
won't take the club's calls after a lowball.
"""

VERSION = 122


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fa_talks (
            league_id      TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id        TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            player_id      TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            week           INTEGER NOT NULL,
            offers         INTEGER NOT NULL DEFAULT 0,
            counter_salary INTEGER,
            counter_years  INTEGER,
            frozen_until   INTEGER,
            PRIMARY KEY (league_id, team_id, player_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fa_talks_player ON fa_talks(player_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fa_talks_team ON fa_talks(team_id)")
