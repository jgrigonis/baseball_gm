"""
Season awards by position (src/league/awards.py): Gold Gloves and Silver
Sluggers are given at each position, so season_awards gets a position
column ('' for every other award) and it joins the primary key.

The Pitching Champion becomes the ERA Champion, beside a new Wins
Champion. Seasons whose awards were already decided are opened again, so
the new awards are decided on the league's next sim; the awards they
already have are kept.
"""

VERSION = 53


def upgrade(conn):
    conn.execute(
        "ALTER TABLE season_awards ADD COLUMN IF NOT EXISTS"
        " position TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE season_awards DROP CONSTRAINT IF EXISTS season_awards_pkey"
    )
    conn.execute(
        "ALTER TABLE season_awards ADD PRIMARY KEY (season_id, award, scope, position)"
    )
    conn.execute(
        "UPDATE season_awards SET award = 'era_champ' WHERE award = 'pitching_champ'"
    )
    conn.execute(
        "UPDATE league_seasons SET awards_regular = FALSE, awards_done = FALSE"
        " WHERE awards_regular"
    )
