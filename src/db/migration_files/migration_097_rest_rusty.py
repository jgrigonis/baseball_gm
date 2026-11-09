"""
Rest rusty players (Josh, 2026-11-09): a Strategy tab checkbox. When it's on,
players still rusty from an injury sit until it fades: Rebuild and Auto-fill
leave them out, the bullpen gives them no role, and on game day they're
treated like the injured (src/league/play_season.py). Off by default, which
is how rust was always handled.
"""

VERSION = 97


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_profiles ADD COLUMN IF NOT EXISTS"
        " rest_rusty BOOLEAN NOT NULL DEFAULT FALSE"
    )
