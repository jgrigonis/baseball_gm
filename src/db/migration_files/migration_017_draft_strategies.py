# src/db/migration_files/migration_017_draft_strategies.py
"""
Draft strategies.

Instead of ordering the whole prospect pool, a GM can save need chips, an age
preference and a few pinned players for a draft. The Blitz draft uses them
after any hand-ordered preference list (see src/league/offseason/draft_strategy.py).
"""

VERSION = 17


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draft_strategies (
            gm_id      TEXT   NOT NULL REFERENCES gms(id)    ON DELETE CASCADE,
            draft_id   TEXT   NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
            chips      JSONB  NOT NULL DEFAULT '{}',
            age_pref   REAL   NOT NULL DEFAULT 0,
            pins       TEXT[] NOT NULL DEFAULT '{}',
            updated_at TEXT   NOT NULL DEFAULT (NOW()),
            PRIMARY KEY (gm_id, draft_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_draft_strategies_draft ON draft_strategies(draft_id)"
    )
