# src/db/migration_files/migration_049_league_news.py
"""
The league news feed (plans/news-feed.md): league_news holds one row per
story, written by src/api/services/news/ after each sim job and each trade.

- league_seasons.news_through: the last league date the feed has covered in
  that season, so each run picks up where the last one stopped.
- league_seasons.news_closed: the season is over and its wrap-up stories are
  written; nothing more to do for it.
- gms.news_seen_id: the newest story the GM has seen, for the News tab's
  badge.

Leagues already running start their feed from the next sim, without stories
for what happened before (src/api/services/news/__init__.py).
"""

VERSION = 49


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS league_news (
            id          BIGSERIAL PRIMARY KEY,
            league_id   TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            season_id   TEXT REFERENCES seasons(id) ON DELETE CASCADE,
            news_date   TEXT NOT NULL,
            kind        TEXT NOT NULL,
            key         TEXT NOT NULL,
            headline    TEXT NOT NULL,
            body        TEXT NOT NULL DEFAULT '',
            weight      INTEGER NOT NULL DEFAULT 1 CHECK (weight BETWEEN 1 AND 3),
            team_ids    TEXT[] NOT NULL DEFAULT '{}',
            player_ids  TEXT[] NOT NULL DEFAULT '{}',
            gm_ids      TEXT[] NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (league_id, key)
        )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_league_news_feed
           ON league_news(league_id, news_date DESC, id DESC)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_league_news_teams ON league_news USING GIN (team_ids)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_league_news_season ON league_news(season_id)"
    )
    conn.execute(
        "ALTER TABLE league_seasons ADD COLUMN IF NOT EXISTS news_through TEXT"
    )
    conn.execute(
        "ALTER TABLE league_seasons ADD COLUMN IF NOT EXISTS"
        " news_closed BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute("ALTER TABLE gms ADD COLUMN IF NOT EXISTS news_seen_id BIGINT")
