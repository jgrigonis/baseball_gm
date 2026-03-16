# src/db/init.py

from src.db.schema import SCHEMA_SQL
from src.db.migrations import run_migrations


def init_db(conn):
    """
    Ensure the database schema exists.
    Safe to call multiple times (idempotent).

    Args:
        conn: SQLite database connection

    Raises:
        sqlite3.Error: If schema creation or migrations fail
    """
    try:
        # CRITICAL: Enable foreign key enforcement
        conn.execute("PRAGMA foreign_keys = ON")
        # Create schema (CREATE TABLE IF NOT EXISTS makes this idempotent)
        conn.executescript(SCHEMA_SQL)

        # Run any pending migrations
        run_migrations(conn)

        # Commit all changes
        conn.commit()

    except Exception:
        # Rollback on any error to maintain clean state
        conn.rollback()
        raise


def verify_schema(conn):
    """
    Verify that the database schema is properly initialized.

    Args:
        conn: SQLite database connection

    Returns:
        bool: True if schema is valid

    Raises:
        RuntimeError: If critical tables are missing
    """
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    tables = {row[0] for row in cursor.fetchall()}

    # Critical tables that must exist
    required_tables = {
        "schema_migrations",
        "players",
        "player_skills",
        "teams",
        "leagues",
        "seasons",
        "games",
    }

    missing = required_tables - tables
    if missing:
        raise RuntimeError(f"Missing required tables: {missing}")

    return True
