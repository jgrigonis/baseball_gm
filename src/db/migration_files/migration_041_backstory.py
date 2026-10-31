# src/db/migration_files/migration_041_backstory.py
"""
League backstory (plans/league-backstory.md): a new league starts with past
seasons generated from its rosters instead of an empty history.

- leagues.backstory_years: how many past seasons a league gets when it
  starts (0 for none). Leagues that already started have none.
- seasons.is_backstory: a generated past season. It has standings, playoff
  series, stat lines and All-Stars but no box scores, and doesn't count
  toward the league's number of seasons.
"""

VERSION = 41


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS"
        " backstory_years INTEGER NOT NULL DEFAULT 5"
    )
    conn.execute("UPDATE leagues SET backstory_years = 0 WHERE state <> 'lobby'")
    conn.execute(
        "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS"
        " is_backstory BOOLEAN NOT NULL DEFAULT FALSE"
    )
