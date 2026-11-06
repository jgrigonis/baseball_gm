# src/db/migration_files/migration_086_last_login.py
"""
When a user last signed in (users.last_login_at): set on sign-in, sign-up,
picking a password and resetting one. Shown on /admin/users.

Nobody's sign-ins were recorded before this, so everyone starts blank.
"""

VERSION = 86


def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
