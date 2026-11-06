# src/db/migration_files/migration_088_hall_of_fame.py
"""
The Hall of Fame (src/league/hall_of_fame.py, plans/hall-of-fame.md).

- hall_elections: one row per league and played season that held an
  election, with how many ballots were cast.
- hall_ballot: one row per player on that year's ballot: votes, share,
  year on the ballot, the outcome (elected / returning / dropped / final),
  the team he gave the most to, and the career numbers the writers saw.
"""

VERSION = 88


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS hall_elections (
            season_id  TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
            league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            year       INTEGER NOT NULL,
            ballots    INTEGER NOT NULL DEFAULT 0,
            decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hall_elections_league"
        " ON hall_elections(league_id, year)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS hall_ballot (
            season_id      TEXT NOT NULL REFERENCES hall_elections(season_id)
                               ON DELETE CASCADE,
            player_id      TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            league_id      TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            votes          INTEGER NOT NULL DEFAULT 0,
            share          REAL NOT NULL DEFAULT 0,
            year_on_ballot INTEGER NOT NULL DEFAULT 1,
            outcome        TEXT NOT NULL,
            team_id        TEXT REFERENCES teams(id) ON DELETE SET NULL,
            summary        JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (season_id, player_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hall_ballot_player ON hall_ballot(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hall_ballot_team ON hall_ballot(team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hall_ballot_league"
        " ON hall_ballot(league_id, outcome)"
    )
