# src/db/migration_files/migration_003_usernames.py
"""
Password logins.

Adds users.username (the login name, unique ignoring case). users.password_hash
already existed but was never written. Existing guests keep NULL in both and
are asked to choose a username and password the next time they visit with
their session cookie.
"""

VERSION = 3


def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower "
        "ON users (lower(username))"
    )
