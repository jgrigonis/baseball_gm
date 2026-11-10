"""
Injury lineup (Josh, 2026-11-10): a Strategy tab setting, in the Injuries
panel next to Rest rusty players, for what the coach does to a person's
saved batting orders when a hitter is hurt. Always auto-fill (the default,
how it always worked) plays the saved lineup and fills the missing man's
slot for the day. The other steps rebuild both batting orders and save them
when a hitter goes out for longer than 10, 7, 5, 3, 2 or 1 days, or at all
(Always rebuild), and again
when he's back and when his rust wears off (src/league/injury_lineup.py).
injury_lineup_key is who was out the last time the sim looked, so it can
tell when that changes.
"""

VERSION = 111


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles ADD COLUMN IF NOT EXISTS"
        " injury_lineup TEXT NOT NULL DEFAULT 'fill'"
        " CHECK (injury_lineup IN ('fill', 'fill-10', 'fill-7', 'fill-5',"
        " 'fill-3', 'fill-2', 'fill-1', 'rebuild'))"
    )
    conn.execute(
        "ALTER TABLE gm_profiles ADD COLUMN IF NOT EXISTS injury_lineup_key TEXT"
    )
