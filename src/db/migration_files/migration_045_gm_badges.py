# src/db/migration_files/migration_045_gm_badges.py
"""
GM badges (plans/gm-profile-page.md, phase 2).

- gm_badges: the badges each person has earned (src/api/services/badges.py).
- users.is_contributor: paid for the game, set by an admin for now.
- gm_career_seasons gets finish/finish_of (place in the division), sweeps
  and trades, which some badges need.

Then refills the career rows of people still in their leagues, so the new
columns are filled in, and awards everyone the badges they've already earned.
"""

VERSION = 45


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gm_badges (
               user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               badge     TEXT NOT NULL,
               detail    TEXT,
               earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (user_id, badge)
           )"""
    )
    conn.execute(
        """ALTER TABLE users ADD COLUMN IF NOT EXISTS
               is_contributor BOOLEAN NOT NULL DEFAULT FALSE"""
    )
    for col in (
        "finish INTEGER",
        "finish_of INTEGER",
        "sweeps INTEGER NOT NULL DEFAULT 0",
        "trades INTEGER NOT NULL DEFAULT 0",
    ):
        conn.execute(f"ALTER TABLE gm_career_seasons ADD COLUMN IF NOT EXISTS {col}")
    # Final rows never change, so open up the ones that can be worked out
    # again (the person still runs the team) and let the backfill redo them.
    conn.execute(
        """UPDATE gm_career_seasons c SET final = FALSE
           WHERE EXISTS (SELECT 1 FROM gms g
                         WHERE g.league_id = c.league_id AND g.user_id = c.user_id)"""
    )
    from src.api.services import badges, career

    career.backfill(conn)
    badges.award_everyone(conn)
