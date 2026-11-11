"""
Waiver alerts (Josh, 2026-11-11): when a person releases a B- or better
player, the other people in the league get a gm_notifications row of kind
'waivers' so they can claim him (src/api/services/news/moves.py).
"""

VERSION = 118


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster', 'trade', 'rust',
                           'settings', 'waivers'))"""
    )
