# src/db/migration_files/migration_017_login_failures.py
"""
Failed sign-ins.

One row per wrong password, by username and IP, so too many guesses at one
account, or from one address, are turned away for a while (see
src/api/services/login_limits.py). Also indexes password_resets by IP, which
caps how many reset emails one address can ask for.
"""

VERSION = 17


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_failures (
            id         BIGSERIAL PRIMARY KEY,
            username   TEXT NOT NULL,
            ip         TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_failures_username "
        "ON login_failures(username, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_failures_ip "
        "ON login_failures(ip, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_resets_ip "
        "ON password_resets(requested_ip, created_at)"
    )
