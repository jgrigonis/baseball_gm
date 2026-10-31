"""
The All-Star Game (plans/all-star-game.md, phase 2): the game itself, with its
two captains, and whether each one left his picks to the scouts
(all_star_games), the captains' draft of the All-Stars
(all_star_picks), and each player's line in the game (all_star_game_stats),
kept apart from the season's stats. all_stars gets each player's stat score
at the vote, which orders the draft board and the AI captains' picks.
"""

VERSION = 35


def upgrade(conn):
    conn.execute(
        "ALTER TABLE all_stars ADD COLUMN IF NOT EXISTS score REAL NOT NULL DEFAULT 0"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_star_games (
            season_id    TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
            captain1_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            captain2_team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            state        TEXT NOT NULL DEFAULT 'draft'
                             CHECK (state IN ('tie', 'draft', 'played')),
            tied_ids     TEXT[] NOT NULL DEFAULT '{}',
            auto1        BOOLEAN NOT NULL DEFAULT FALSE,
            auto2        BOOLEAN NOT NULL DEFAULT FALSE,
            game_date    TEXT,
            score1       INTEGER,
            score2       INTEGER,
            innings      INTEGER,
            line_score   JSONB,
            mvp_player_id TEXT REFERENCES players(id) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_star_picks (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            side       INTEGER NOT NULL CHECK (side IN (1, 2)),
            pick       INTEGER NOT NULL,
            PRIMARY KEY (season_id, player_id),
            UNIQUE (season_id, pick)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_star_game_stats (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            side       INTEGER NOT NULL CHECK (side IN (1, 2)),
            position   TEXT,
            batting_order INTEGER,
            bat_ab     INTEGER NOT NULL DEFAULT 0,
            bat_runs   INTEGER NOT NULL DEFAULT 0,
            bat_hits   INTEGER NOT NULL DEFAULT 0,
            bat_doubles INTEGER NOT NULL DEFAULT 0,
            bat_triples INTEGER NOT NULL DEFAULT 0,
            bat_home_runs INTEGER NOT NULL DEFAULT 0,
            bat_rbi    INTEGER NOT NULL DEFAULT 0,
            bat_walks  INTEGER NOT NULL DEFAULT 0,
            bat_strike_outs INTEGER NOT NULL DEFAULT 0,
            bat_stolen_bases INTEGER NOT NULL DEFAULT 0,
            pitch_order INTEGER,
            pitch_outs INTEGER NOT NULL DEFAULT 0,
            pitch_hits INTEGER NOT NULL DEFAULT 0,
            pitch_runs INTEGER NOT NULL DEFAULT 0,
            pitch_earned_runs INTEGER NOT NULL DEFAULT 0,
            pitch_walks INTEGER NOT NULL DEFAULT 0,
            pitch_strike_outs INTEGER NOT NULL DEFAULT 0,
            pitch_home_runs INTEGER NOT NULL DEFAULT 0,
            pitch_win  BOOLEAN NOT NULL DEFAULT FALSE,
            pitch_loss BOOLEAN NOT NULL DEFAULT FALSE,
            pitch_save BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (season_id, player_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_games_c1 ON all_star_games(captain1_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_games_c2 ON all_star_games(captain2_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_games_mvp ON all_star_games(mvp_player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_picks_player ON all_star_picks(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_all_star_game_stats_player"
        " ON all_star_game_stats(player_id)"
    )
