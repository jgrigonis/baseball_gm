# src/db/migration_files/migration_134_news_hidden.py
"""
News you can hide (Josh, 2026-11-14): an x on each story on the News tab
hides it for that GM (news_hidden), with a Hidden list to bring stories
back, and a filter that turns whole kinds of story off
(gms.news_hidden_kinds, league_news.kind values).
"""

VERSION = 134


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS news_hidden (
    gm_id    TEXT NOT NULL REFERENCES gms(id) ON DELETE CASCADE,
    news_id  BIGINT NOT NULL REFERENCES league_news(id) ON DELETE CASCADE,
    PRIMARY KEY (gm_id, news_id)
)"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_news_hidden_news ON news_hidden(news_id)"
    )
    conn.execute(
        "ALTER TABLE gms ADD COLUMN IF NOT EXISTS"
        " news_hidden_kinds TEXT[] NOT NULL DEFAULT '{}'"
    )
