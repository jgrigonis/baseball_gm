"""
All-Star reserves (plans/all-star-game.md): an All-Star who's hurt keeps the
honor but sits out the draft and the game, and the next best healthy player
at his position takes his place. all_stars.replaces is the injured All-Star
a reserve stands in for.
"""

VERSION = 36


def upgrade(conn):
    conn.execute(
        """ALTER TABLE all_stars ADD COLUMN IF NOT EXISTS replaces TEXT
               REFERENCES players(id) ON DELETE SET NULL"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_stars_replaces ON all_stars(replaces)"
    )
