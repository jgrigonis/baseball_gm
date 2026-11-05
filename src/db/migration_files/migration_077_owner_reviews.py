"""
Owners' season reviews (src/api/services/owner_review.py): which owner judged
the season, their verdict as a score from -1 to 1, the GM's job security
after it (0 to 100), and the detail (each dimension's score and the facts).
"""

VERSION = 77


def upgrade(conn):
    for col, kind in (
        ("owner_id", "TEXT"),
        ("score", "REAL"),
        ("job_security", "INTEGER"),
        ("detail", "JSONB"),
    ):
        conn.execute(
            f"ALTER TABLE gm_season_evaluations ADD COLUMN IF NOT EXISTS {col} {kind}"
        )
