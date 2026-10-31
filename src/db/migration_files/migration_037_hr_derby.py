"""
The Home Run Derby (plans/all-star-game.md, phase 3): every hitter's line in
every matchup of a season's derby (hr_derby_results). Round 1 is the field;
the last round's winner is the champion.
"""

VERSION = 37


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_derby_results (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            round      INTEGER NOT NULL,
            match      INTEGER NOT NULL,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            team_id    TEXT REFERENCES teams(id) ON DELETE SET NULL,
            seed       INTEGER NOT NULL,
            homers     INTEGER NOT NULL DEFAULT 0,
            swingoff   INTEGER,
            longest    INTEGER NOT NULL DEFAULT 0,
            won        BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (season_id, round, player_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_derby_results_player"
        " ON hr_derby_results(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hr_derby_results_team"
        " ON hr_derby_results(team_id)"
    )
