# src/db/migration_files/migration_138_live_draft.py
"""
Long Form's live draft (Josh, 2026-11-14; src/api/services/live_draft.py).

- leagues.pick_timer_sec: seconds a person has for each pick in a
  multiplayer live draft (default 90). A one-person league has no timer.
- drafts.pick_deadline: when the pick on the clock runs out, or NULL when no
  clock is running (an AI pick, a one-person league, or no live draft).
- draft_order.auto: the team's person left the rest of their picks to the
  scouts, who take the default pick each time.
"""

VERSION = 138


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS pick_timer_sec INTEGER NOT NULL DEFAULT 90"
    )
    conn.execute("ALTER TABLE drafts ADD COLUMN IF NOT EXISTS pick_deadline TIMESTAMPTZ")
    conn.execute(
        "ALTER TABLE draft_order ADD COLUMN IF NOT EXISTS auto BOOLEAN NOT NULL DEFAULT FALSE"
    )
