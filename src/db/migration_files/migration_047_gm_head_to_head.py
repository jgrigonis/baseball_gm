# src/db/migration_files/migration_047_gm_head_to_head.py
"""
GM profile, phase 4 (plans/gm-profile-page.md): gm_head_to_head keeps each
person's record against the other people in their leagues, for the Rivals
section, since games go with the league.

Then fills it from the leagues that are still around. Career rows that are
final are skipped by the backfill, so it opens up the seasons of people
still in their leagues first, as migration 046 did.
"""

VERSION = 47


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gm_head_to_head (
            user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            opponent_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            league_id       TEXT NOT NULL,
            season_id       TEXT NOT NULL,
            league_name     TEXT NOT NULL,
            season_year     INTEGER NOT NULL,
            team_city       TEXT NOT NULL,
            team_mascot     TEXT NOT NULL,
            opponent_city   TEXT NOT NULL,
            opponent_mascot TEXT NOT NULL,
            wins            INTEGER NOT NULL DEFAULT 0,
            losses          INTEGER NOT NULL DEFAULT 0,
            series_round    TEXT,
            series_won      BOOLEAN,
            final           BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, opponent_id, league_id, season_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gm_h2h_opponent ON gm_head_to_head(opponent_id)"
    )
    conn.execute(
        """UPDATE gm_career_seasons c SET final = FALSE
           WHERE EXISTS (SELECT 1 FROM gms g
                         WHERE g.league_id = c.league_id AND g.user_id = c.user_id)"""
    )
    from src.api.services import career

    career.backfill(conn)
