# src/db/migration_files/migration_135_blitz_no_bidding.py
"""
Speed Blitz has no money (Josh, 2026-11-14): its free agents just sign, so
a Speed Blitz league caught with bidding open closes it. New ones never open
it (LeagueRepository.set_state).
"""

VERSION = 135


def upgrade(conn):
    conn.execute(
        "UPDATE leagues SET fa_bidding = FALSE WHERE mode = 'speed_blitz' AND fa_bidding"
    )
