"""
Player contracts (src/player/contracts.py). Makes player_contracts and signs
everyone on a team in every league that has started, for its newest
season: rookie deals for players drafted in the last three seasons, standard
deals partway through for everyone else.
"""

from src.db.repositories.contract_repo import ContractRepository

VERSION = 61


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_contracts (
            id          SERIAL PRIMARY KEY,
            player_id   TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            team_id     TEXT REFERENCES teams(id) ON DELETE SET NULL,
            kind        TEXT NOT NULL CHECK (kind IN ('rookie', 'standard')),
            salary      INTEGER NOT NULL CHECK (salary > 0),
            start_year  INTEGER NOT NULL,
            years       INTEGER NOT NULL CHECK (years >= 1),
            pick_number INTEGER,
            created_at  TEXT NOT NULL DEFAULT (NOW()),
            UNIQUE (player_id, start_year)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_contracts_league"
        " ON player_contracts(league_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_contracts_team"
        " ON player_contracts(team_id)"
    )

    rows = conn.execute(
        """
        SELECT l.id AS league_id, MAX(s.year) AS year
        FROM leagues l
        JOIN league_seasons ls ON ls.league_id = l.id
        JOIN seasons s ON s.id = ls.season_id
        WHERE l.state <> 'lobby'
        GROUP BY l.id
        """
    ).fetchall()
    repo = ContractRepository(conn)
    for r in rows:
        repo.sign_unsigned(r["league_id"], r["year"])
