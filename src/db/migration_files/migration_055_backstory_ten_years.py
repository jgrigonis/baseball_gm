"""
A new league starts with ten past seasons of history instead of five
(DEFAULT_BACKSTORY_YEARS), and the lobby says when a league's start has got
to generating that history:

- leagues.backstory_years defaults to 10. Leagues still in the lobby on the
  old default of 5 move up to 10; any other number was set by an admin and
  is kept.
- sim_jobs.stage: what a running job is doing now, for the page polling it
  (e.g. "Simulating league history…"). NULL when there's nothing to say.
"""

VERSION = 55


def upgrade(conn):
    conn.execute("ALTER TABLE leagues ALTER COLUMN backstory_years SET DEFAULT 10")
    conn.execute(
        "UPDATE leagues SET backstory_years = 10"
        " WHERE state = 'lobby' AND backstory_years = 5"
    )
    conn.execute("ALTER TABLE sim_jobs ADD COLUMN IF NOT EXISTS stage TEXT")
