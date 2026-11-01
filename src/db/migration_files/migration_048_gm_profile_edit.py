# src/db/migration_files/migration_048_gm_profile_edit.py
"""
GM profile, phase 5 (plans/gm-profile-page.md): a one-line bio and a
favorite team (a World League city), set from Edit profile.
"""

VERSION = 48


def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_team TEXT")
