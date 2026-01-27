# A migration is:
# “A small, one-way transformation that moves the database schema from
# version N to N+1.”

# Called once, versioned, explicit.

# Notes:
# SQLite migrations are hard to roll back.

# So:
# Avoid destructive changes
# Prefer adding columns/tables
# If you must remove something → create a new table and migrate data

# If you delete migration_003 locally and recreate it:

# Use migration_004 instead

# Gaps are fine.
# Rewrites are not.

# src/db/migrations.py

from datetime import datetime
from datetime import UTC
from src.db.migration_files.runner import load_migrations


def run_migrations(conn):
    """
    Run all the migrations.
    """
    _ensure_migration_table(conn)
    applied = _applied_versions(conn)

    for version, migrate in load_migrations():
        if version not in applied:
            migrate(conn)
            _record_migration(conn, version)

    conn.commit()


def _ensure_migration_table(conn):
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """
    )


def _applied_versions(conn):
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _record_migration(conn, version):
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, datetime.now(UTC).isoformat()),
    )
