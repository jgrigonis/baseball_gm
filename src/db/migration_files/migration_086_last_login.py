# src/db/migration_files/migration_086_last_login.py
"""
When a user last signed in and was last seen.

- users.last_login_at: set on sign-in, sign-up, picking a password and
  resetting one. Shown on the admin page for one user.
- users.last_seen_at: set when a signed-in user loads a page, at most every
  few minutes (sign-in cookies last years, so this is the useful one).
  Shown on /admin/users.

Neither was recorded before this, so everyone starts blank.
"""

VERSION = 86


def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ")
