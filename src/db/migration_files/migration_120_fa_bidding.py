# src/db/migration_files/migration_120_fa_bidding.py
"""
Free agent bidding through the preseason (Josh, 2026-11-12). Bids open with
the draft and stay open into the preseason, until they settle: a Close
Bidding step in a solo league, the first preseason period in a multiplayer
one (src/api/services/offseason_fa.py close_bidding). leagues.fa_bidding is
true while they're open. A league in its draft now has them open; one past
it already settled them when its draft ran.
"""

VERSION = 120


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS fa_bidding BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute("UPDATE leagues SET fa_bidding = TRUE WHERE state = 'draft'")
