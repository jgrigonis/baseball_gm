"""
Specific injuries (plans/injury-details.md, phase 1): each injury records
which one it was (torn ACL, hamstring strain, ...) as a key into
src/player/injury_types.py. Older injuries keep NULL and show their severity.
"""

VERSION = 57


def upgrade(conn):
    conn.execute(
        "ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS injury_type TEXT"
    )
    conn.execute(
        "ALTER TABLE player_injury_log ADD COLUMN IF NOT EXISTS injury_type TEXT"
    )
