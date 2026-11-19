"""
Bid results (Josh, 2026-11-19): when free agent bidding closes, each person
hears what happened to every bid they made, won or lost and why, as
gm_notifications of kind 'bids' (src/api/services/offseason_fa.py
close_bidding), shown on the sim card.
"""

VERSION = 148


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster', 'trade', 'rust',
                           'settings', 'waivers', 'bids'))"""
    )
