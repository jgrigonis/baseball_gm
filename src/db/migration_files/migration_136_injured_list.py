# src/db/migration_files/migration_136_injured_list.py
"""
Long Form's injured list (Josh, 2026-11-14; plans/injury-details.md phase
4): a hurt player placed on the 7-day (concussions), 10-day (hitters),
15-day (pitchers) or 60-day IL comes off the active roster. The 60-day IL
frees his 40-man spot too. He can't come back before eligible_on.
activated_on is set when he comes off the list.
"""

VERSION = 136


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS injured_list (
    id            SERIAL PRIMARY KEY,
    league_id     TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    team_id       TEXT NOT NULL,
    player_id     TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    kind          INTEGER NOT NULL CHECK (kind IN (7, 10, 15, 60)),
    placed_on     DATE NOT NULL,
    eligible_on   DATE NOT NULL,
    activated_on  DATE
)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_injured_list_team"
        " ON injured_list(team_id) WHERE activated_on IS NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_injured_list_league ON injured_list(league_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_injured_list_player ON injured_list(player_id)"
    )
