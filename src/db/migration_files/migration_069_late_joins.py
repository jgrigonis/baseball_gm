# src/db/migration_files/migration_069_late_joins.py
"""
People can join a league after it starts, by taking over a team an AI GM
runs, between seasons (src/api/services/takeover.py).

leagues.late_joins is the commissioner's switch for it, on unless they turn
it off. gms.joined_year is the first season a GM's career record counts: a
person who takes over a team isn't credited with the seasons it played
before they got there. NULL counts every season, as for anyone who was
there from the start.
"""

VERSION = 69


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS"
        " late_joins BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS joined_year INTEGER")
