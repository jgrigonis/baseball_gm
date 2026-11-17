# src/db/migration_files/migration_141_draft_class_grade.py
"""
Class grade vs now grade (Josh, 2026-11-17): the Draft board grades a
prospect against his draft class, every other screen against pros. The
class grade he had on draft day is kept with the pick, so his roster row
and player panel can say "class A-" after his skills move on. Picks made
before this have none.
"""

VERSION = 141


def upgrade(conn):
    conn.execute("ALTER TABLE draft_picks ADD COLUMN IF NOT EXISTS class_grade TEXT")
