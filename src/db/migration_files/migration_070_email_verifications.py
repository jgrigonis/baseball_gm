# src/db/migration_files/migration_070_email_verifications.py
"""
Email verification (src/api/services/email_verify.py).

email_verifications: one row per emailed verify link. Like password_resets,
only a SHA-256 hash of the token is kept. Each row remembers the address it
was sent to, so a link sent before the email was changed can't verify the
new one. users.is_verified (in the schema since the start, unused until now)
is set when a link is used, and cleared when the email changes.
"""

VERSION = 70


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS email_verifications (
               id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
               user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
               email        TEXT NOT NULL,
               token_hash   TEXT UNIQUE NOT NULL,
               created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
               expires_at   TIMESTAMPTZ NOT NULL,
               used_at      TIMESTAMPTZ
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_verifications_user"
        " ON email_verifications(user_id, created_at)"
    )
    # Nothing ever verified anyone, but make sure no one starts out verified.
    conn.execute("UPDATE users SET is_verified = FALSE WHERE is_verified")
