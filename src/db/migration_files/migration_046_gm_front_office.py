# src/db/migration_files/migration_046_gm_front_office.py
"""
GM profile, phase 3 (plans/gm-profile-page.md): gm_career_seasons keeps
where the team's front office saw it each season (the last team_states
state), for the GM style section, since team_states goes with the league.

Then refills the career rows of people still in their leagues, so the new
column is filled in.
"""

VERSION = 46


def upgrade(conn):
    conn.execute(
        "ALTER TABLE gm_career_seasons ADD COLUMN IF NOT EXISTS front_office TEXT"
    )
    # Final rows never change, so open up the ones that can be worked out
    # again (the person still runs the team) and let the backfill redo them.
    conn.execute(
        """UPDATE gm_career_seasons c SET final = FALSE
           WHERE EXISTS (SELECT 1 FROM gms g
                         WHERE g.league_id = c.league_id AND g.user_id = c.user_id)"""
    )
    from src.api.services import career

    career.backfill(conn)
