"""
Team states (src/league/team_state.py): where each front office sees its
team, stored at checkpoints through the season, with the inputs behind it.
"""

VERSION = 25


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS team_states (
            id         BIGSERIAL PRIMARY KEY,
            league_id  TEXT NOT NULL,
            season_id  TEXT NOT NULL,
            team_id    TEXT NOT NULL,
            as_of      TEXT NOT NULL,
            state      TEXT NOT NULL CHECK (state IN (
                           'all-in', 'contending', 'retooling',
                           'ramping-up', 'rebuilding', 'aging-out'
                       )),
            held       INTEGER NOT NULL DEFAULT 1,
            candidate  TEXT NOT NULL,
            inputs     JSONB NOT NULL,
            created_at TEXT NOT NULL DEFAULT (NOW()),

            FOREIGN KEY (league_id) REFERENCES leagues(id) ON DELETE CASCADE,
            FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
            FOREIGN KEY (team_id)   REFERENCES teams(id)   ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_states_team "
        "ON team_states(team_id, season_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_states_league "
        "ON team_states(league_id, season_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_states_season ON team_states(season_id)"
    )
