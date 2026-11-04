"""
Home region (plans/player-happiness.md, phase 0): every player is from one of
the team pool's regions (players.home_region, src/player/home_region.py).
Existing players get the same region a new player with their id would.
"""

from src.player.home_region import home_region_for

VERSION = 64


def upgrade(conn):
    conn.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS home_region TEXT")
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM players WHERE home_region IS NULL"
        ).fetchall()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE players SET home_region = %s WHERE id = %s",
            [(home_region_for(pid), pid) for pid in ids],
        )
