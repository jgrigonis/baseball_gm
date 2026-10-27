# src/db/migration_files/migration_016_password_resets.py
"""
Password reset links.

A forgotten password is reset through a link emailed to the account's
address. Each row is one link: only a SHA-256 hash of its token is stored, it
works for an hour, and only once (see src/api/services/password_reset.py).
"""

VERSION = 16


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_resets (
            id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash   TEXT UNIQUE NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at   TIMESTAMPTZ NOT NULL,
            used_at      TIMESTAMPTZ,
            requested_ip TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id)"
    )
