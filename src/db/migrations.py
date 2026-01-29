# src/db/migrations.py

"""
Migration System

A migration is a small, one-way transformation that moves the database
schema from version N to N+1.

Migrations are:
- Called once
- Versioned
- Explicit

Important Notes:
- SQLite migrations are hard to roll back
- Avoid destructive changes
- Prefer adding columns/tables
- If you must remove something → create a new table and migrate data

Versioning Rules:
- If you delete migration_003 locally and recreate it, use migration_004 instead
- Gaps in version numbers are fine
- Rewrites are not allowed (breaks deployed databases)
"""

from datetime import datetime
from datetime import UTC
from src.db.migration_files.runner import load_migrations


def run_migrations(conn):
    """
    Run all pending migrations in order.

    Args:
        conn: SQLite database connection

    Raises:
        Exception: If any migration fails (after rollback)
    """
    _ensure_migration_table(conn)
    applied = _applied_versions(conn)

    for version, migrate in load_migrations():
        if version not in applied:
            try:
                migrate(conn)
                _record_migration(conn, version)
                conn.commit()  # Commit each migration individually
            except Exception:
                conn.rollback()  # Rollback failed migration
                raise  # Re-raise the error


def _ensure_migration_table(conn):
    """Create the schema_migrations table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _applied_versions(conn):
    """
    Get set of already-applied migration versions.

    Returns:
        set[int]: Version numbers that have been applied
    """
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _record_migration(conn, version):
    """
    Record that a migration has been applied.

    Args:
        conn: SQLite database connection
        version: Migration version number
    """
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, datetime.now(UTC).isoformat()),
    )
