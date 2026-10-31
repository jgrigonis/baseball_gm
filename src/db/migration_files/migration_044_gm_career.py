# src/db/migration_files/migration_044_gm_career.py
"""
GM careers (plans/gm-profile-page.md): one row per person per league season,
kept by src/api/services/career.py and shown on the profile page
(/gms/{username}).

gm_career_seasons has no foreign key to leagues, teams or seasons on purpose:
a person's record has to outlive the league, which is deleted when its last
person leaves. The league and team names are copied in for the same reason.

Then fills it from every league that's still around.
"""

VERSION = 44


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gm_career_seasons (
               user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               league_id      TEXT NOT NULL,
               season_id      TEXT NOT NULL,
               league_name    TEXT NOT NULL,
               season_year    INTEGER NOT NULL,
               team_city      TEXT NOT NULL,
               team_mascot    TEXT NOT NULL,
               wins           INTEGER NOT NULL DEFAULT 0,
               losses         INTEGER NOT NULL DEFAULT 0,
               division_title BOOLEAN NOT NULL DEFAULT FALSE,
               playoff_result TEXT CHECK (playoff_result IN
                                  ('Round 1', 'Semifinals', 'Finals', 'Champion')),
               final          BOOLEAN NOT NULL DEFAULT FALSE,
               updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               PRIMARY KEY (user_id, league_id, season_id)
           )"""
    )
    from src.api.services import career

    career.backfill(conn)
