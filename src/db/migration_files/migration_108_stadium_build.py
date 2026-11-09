"""
New stadiums (Josh, 2026-11-09: the big option, in price tiers, taking
several seasons to build; src/league/finances.py BALLPARK). A project now
records the season it was ordered as well as the one it opens; the owner
pays for it a season at a time in between. NULL ordered: it opened the
season it was ordered.
"""

VERSION = 108


def upgrade(conn):
    conn.execute(
        "ALTER TABLE ballpark_projects ADD COLUMN IF NOT EXISTS ordered INTEGER"
    )
