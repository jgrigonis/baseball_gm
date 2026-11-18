# src/db/migration_files/migration_142_resign_talks.py
"""
Re-sign negotiations (Josh, 2026-11-18): on the Expiring Deals tab a GM can
offer an expiring player a salary and seasons (src/api/services/
resign_offers.py).

- contract_choices.salary / years: the deal he agreed to, when a re-sign
  isn't at his asking price.
- resign_talks: offers made in the window, the counter that stands, and
  whether he was insulted (talks closed; his price went up, or he refused).
- player_grudges: a lowball from his club, taken off his mood next season
  and fading over the weekly updates.
"""

VERSION = 142


def upgrade(conn):
    conn.execute("ALTER TABLE contract_choices ADD COLUMN IF NOT EXISTS salary INTEGER")
    conn.execute("ALTER TABLE contract_choices ADD COLUMN IF NOT EXISTS years INTEGER")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS resign_talks (
    league_id      TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    player_id      TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id        TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    year           INTEGER NOT NULL,
    offers         INTEGER NOT NULL DEFAULT 0,
    counter_salary INTEGER,
    counter_years  INTEGER,
    closed         BOOLEAN NOT NULL DEFAULT FALSE,
    bumped         BOOLEAN NOT NULL DEFAULT FALSE,
    refused        BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (player_id, year)
)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_resign_talks_league ON resign_talks(league_id, year)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_resign_talks_team ON resign_talks(team_id)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS player_grudges (
    league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    year       INTEGER NOT NULL,
    amount     REAL NOT NULL,
    updates    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, team_id)
)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_grudges_league ON player_grudges(league_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_grudges_team ON player_grudges(team_id)"
    )
