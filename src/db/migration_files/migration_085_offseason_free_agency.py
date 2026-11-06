"""
Offseason free agency (free agency phase 2, PR 3; Josh's decisions
2026-11-05; src/api/services/offseason_fa.py).

- contract_choices: what a team decided, in the offseason, about a player
  whose deal runs out: re-sign him now at his price ('resign'), or let him
  go to free agency ('let_go').
- fa_bids: a team's offer to a free agent during the draft (a salary a
  season and a number of seasons). He picks one when the preseason starts.
"""

VERSION = 85


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_choices (
            league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            player_id   TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            year        INTEGER NOT NULL,
            choice      TEXT NOT NULL CHECK (choice IN ('resign', 'let_go')),
            created_at  TEXT NOT NULL DEFAULT (NOW()),
            PRIMARY KEY (player_id, year)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contract_choices_league"
        " ON contract_choices(league_id, year)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contract_choices_team"
        " ON contract_choices(team_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fa_bids (
            league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            player_id   TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            year        INTEGER NOT NULL,
            salary      INTEGER NOT NULL CHECK (salary > 0),
            years       INTEGER NOT NULL CHECK (years >= 1),
            created_at  TEXT NOT NULL DEFAULT (NOW()),
            PRIMARY KEY (player_id, team_id, year)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fa_bids_league ON fa_bids(league_id, year)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fa_bids_team ON fa_bids(team_id)")
