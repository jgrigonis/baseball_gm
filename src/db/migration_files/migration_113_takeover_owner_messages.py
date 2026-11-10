# src/db/migration_files/migration_113_takeover_owner_messages.py
"""
New GMs inherited the old GM's owner mail (Josh, 2026-11-10): taking over a
team (joining a running league, or a new job after a firing) reuses the AI
GM's gms row, and the owner's messages are keyed to that row, so the person
walked into a dozen-plus unread messages written to the AI GMs before them.
take_over now clears them; this clears the ones already inherited: messages
from seasons before the person's first season (gms.joined_year).
"""

VERSION = 113


def upgrade(conn):
    conn.execute(
        """DELETE FROM owner_messages m
           USING gms g, seasons s
           WHERE m.gm_id = g.id AND s.id = m.season_id
             AND NOT g.is_ai AND g.joined_year IS NOT NULL
             AND s.year < g.joined_year"""
    )
