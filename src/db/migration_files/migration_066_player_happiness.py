"""
Player happiness (plans/player-happiness.md): every player gets a
personality (player_personality: public type, drive weights, traits, a
favorite climate), drawn from his id the same way a new player's is, and a
mood per season (player_moods), filled in as games are played.
"""

from psycopg.types.json import Jsonb

from src.player.happiness import personality_for

VERSION = 66


def upgrade(conn):
    for statement in DDL.split(";"):
        if statement.strip():
            conn.execute(statement)
    ids = [
        r["id"]
        for r in conn.execute(
            """SELECT p.id FROM players p
               WHERE NOT EXISTS (
                   SELECT 1 FROM player_personality pp WHERE pp.player_id = p.id)"""
        ).fetchall()
    ]
    rows = []
    for pid in ids:
        pers = personality_for(pid)
        rows.append(
            (pid, pers.type, Jsonb(pers.drives), Jsonb(pers.traits), pers.climate)
        )
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO player_personality
                   (player_id, type, drives, traits, climate)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            rows,
        )


DDL = """
CREATE TABLE IF NOT EXISTS player_personality (
    player_id TEXT PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    type      TEXT NOT NULL,       -- public player type (src/player/happiness.py TYPES)
    drives    JSONB NOT NULL,      -- drive -> weight 0..100
    traits    JSONB NOT NULL,      -- ego, temper, loyalty 0..100
    climate   TEXT                 -- favorite climate, if he has one
);

CREATE TABLE IF NOT EXISTS player_moods (
    player_id  TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season_id  TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    league_id  TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    team_id    TEXT REFERENCES teams(id) ON DELETE SET NULL,
    mood       REAL NOT NULL,      -- -1..1, moves toward target weekly
    target     REAL NOT NULL,      -- what his situation points to
    detail     JSONB NOT NULL,     -- drive -> [satisfaction, reason], and lines
    updated_on TEXT NOT NULL,      -- league date of the last update
    PRIMARY KEY (player_id, season_id)
);
CREATE INDEX IF NOT EXISTS idx_player_moods_league ON player_moods(league_id, season_id);
CREATE INDEX IF NOT EXISTS idx_player_moods_season ON player_moods(season_id);
CREATE INDEX IF NOT EXISTS idx_player_moods_team ON player_moods(team_id);
"""
