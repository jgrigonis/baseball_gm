"""
leagues.injuries_enabled: whether players get hurt in the league. The GM picks
it at creation; Speed Blitz starts with it off and the other modes on. Speed
Blitz leagues made before this never had injuries, so they keep them off.
"""

VERSION = 34


def upgrade(conn):
    cols = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'leagues' AND column_name = 'injuries_enabled'"
    ).fetchone()
    if cols:
        return
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN injuries_enabled BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute(
        "UPDATE leagues SET injuries_enabled = FALSE WHERE mode = 'speed_blitz'"
    )
