"""
Attendance (Josh, 2026-11-11, src/league/finances.py crowd): every home
game records its crowd and the crowd its fans were expected to bring (before
the park's seats cap it). team_budgets records each finished season's
crowds: the total, the games that had one, the expected total (uncapped and
in the park), the park's seats, sellouts, and what the crowds added to or
took off ticket revenue. Games played before this have no crowd and count
as drawing what was expected.
"""

VERSION = 116


def upgrade(conn):
    conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS attendance INTEGER")
    conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS crowd_expected INTEGER")
    for col, kind in (
        ("attendance", "BIGINT"),
        ("crowd_games", "INTEGER"),
        ("crowd_expected", "BIGINT"),
        ("crowd_in_park", "BIGINT"),
        ("capacity", "INTEGER"),
        ("sellouts", "INTEGER"),
        ("crowd_revenue", "BIGINT"),
    ):
        conn.execute(f"ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS {col} {kind}")
