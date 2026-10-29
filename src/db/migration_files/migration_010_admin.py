# src/db/migration_files/migration_010_admin.py
"""
Admins, forced password changes, and pausing a league.

users.is_admin opens the admin pages (/admin/). users.must_change_password
sends a user to the change-password page until they pick a new one; it's set
on the default admin and whenever an admin sets someone's password.
leagues.is_paused stops a league from moving on until an admin resumes it.

Also creates the default admin login, "admin" with the password from
settings.admin_initial_password, which has to be changed at first sign-in.
If someone already registered "admin", nobody is made an admin: run
`python scripts/cligr.py make-admin USERNAME` instead.
"""

import logging
import uuid

from src.api.services.passwords import hash_password
from src.config import settings

VERSION = 10

DEFAULT_ADMIN_USERNAME = "admin"

log = logging.getLogger(__name__)


def upgrade(conn):
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE"
    )

    taken = conn.execute(
        "SELECT 1 FROM users WHERE lower(username) = lower(%s)",
        (DEFAULT_ADMIN_USERNAME,),
    ).fetchone()
    if taken:
        log.warning(
            "No default admin created: the username %r is taken. "
            "Run `python scripts/cligr.py make-admin USERNAME`.",
            DEFAULT_ADMIN_USERNAME,
        )
        return
    password = settings.admin_initial_password
    # Anyone could sign in as admin before the owner does.
    if not password or (settings.served_over_https and password == "changeme"):
        raise RuntimeError(
            "Set ADMIN_INITIAL_PASSWORD before the first deploy: it's the "
            "password for the admin login this creates."
        )
    conn.execute(
        """INSERT INTO users (id, session_token, display_name, username,
                              password_hash, is_admin, must_change_password)
           VALUES (%s, %s, %s, %s, %s, TRUE, TRUE)""",
        (
            str(uuid.uuid4()),
            uuid.uuid4().hex + uuid.uuid4().hex,
            DEFAULT_ADMIN_USERNAME,
            DEFAULT_ADMIN_USERNAME,
            hash_password(password),
        ),
    )
