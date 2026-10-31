"""
The Rookie Game (plans/all-star-game.md, phase 4): the season's best rookies
who aren't All-Stars (rookie_game_players), the game and its captains
(rookie_games), the captains' draft (rookie_game_picks) and each player's
line in the game (rookie_game_stats). The tables are laid out like the
All-Star Game's, so the same code runs both.
"""

VERSION = 38


INDEXES = (
    ("idx_rookie_game_players_player", "rookie_game_players", "player_id"),
    ("idx_rookie_game_players_team", "rookie_game_players", "team_id"),
    ("idx_rookie_game_players_replaces", "rookie_game_players", "replaces"),
    ("idx_rookie_games_c1", "rookie_games", "captain1_team_id"),
    ("idx_rookie_games_c2", "rookie_games", "captain2_team_id"),
    ("idx_rookie_games_mvp", "rookie_games", "mvp_player_id"),
    ("idx_rookie_game_picks_player", "rookie_game_picks", "player_id"),
    ("idx_rookie_game_stats_player", "rookie_game_stats", "player_id"),
)


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rookie_game_players (
            season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            slot       TEXT NOT NULL,
            points     INTEGER NOT NULL DEFAULT 0,
            wildcard   BOOLEAN NOT NULL DEFAULT FALSE,
            score      REAL NOT NULL DEFAULT 0,
            replaces   TEXT REFERENCES players(id) ON DELETE SET NULL,
            PRIMARY KEY (season_id, player_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rookie_games (
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
        CREATE TABLE IF NOT EXISTS rookie_game_picks (
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
        CREATE TABLE IF NOT EXISTS rookie_game_stats (
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
    for name, table, col in INDEXES:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({col})")
