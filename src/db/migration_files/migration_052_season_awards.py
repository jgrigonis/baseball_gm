"""
Season awards (src/league/awards.py, src/api/services/awards.py): one row
per award a season handed out. Awards given in each of the two leagues
(Atlantic and Pacific) have the league's name as their scope; awards given
once for everyone, or in a league without divisions, have ''.

- league_seasons.awards_regular: the regular season awards are decided.
- league_seasons.awards_done: every award the season will have is decided,
  so it isn't looked at again.

Seasons already over get their awards on the league's next sim job, except
GM of the Year (who ran each team back then isn't kept).
"""

VERSION = 52


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS season_awards (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            award      TEXT NOT NULL,
            scope      TEXT NOT NULL DEFAULT '',
            player_id  TEXT REFERENCES players(id) ON DELETE CASCADE,
            team_id    TEXT REFERENCES teams(id) ON DELETE CASCADE,
            gm_id      TEXT REFERENCES gms(id) ON DELETE SET NULL,
            line       TEXT NOT NULL DEFAULT '',
            value      REAL,
            decided_on TEXT,
            PRIMARY KEY (season_id, award, scope)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_season_awards_player ON season_awards(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_season_awards_gm ON season_awards(gm_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_season_awards_team ON season_awards(team_id)"
    )
    conn.execute(
        "ALTER TABLE league_seasons ADD COLUMN IF NOT EXISTS"
        " awards_regular BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE league_seasons ADD COLUMN IF NOT EXISTS"
        " awards_done BOOLEAN NOT NULL DEFAULT FALSE"
    )
