"""
Games keep their runs by inning (line_score: {"away": [...], "home": [...]}),
so the game panel can show a line score. Games played before this have none
and show only their R/H/E.
"""

VERSION = 32


def upgrade(conn):
    conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS line_score JSONB")
