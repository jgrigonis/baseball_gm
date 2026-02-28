# tests/db/test_init.py

import pytest
import sqlite3

from src.db.init import init_db, verify_schema


def test_init_db_creates_schema():
    """Test that init_db creates all required tables"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    init_db(conn)

    # Verify schema is valid
    assert verify_schema(conn)

    conn.close()


def test_init_db_is_idempotent():
    """Test that init_db can be called multiple times safely"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Call multiple times
    init_db(conn)
    init_db(conn)
    init_db(conn)

    # Should still be valid
    assert verify_schema(conn)

    conn.close()


def test_init_db_rolls_back_on_error():
    """Test that init_db rolls back if migrations fail"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Mock run_migrations to raise an error
    import src.db.init as init_module

    original_run_migrations = init_module.run_migrations

    def failing_migrations(conn):
        raise sqlite3.OperationalError("Migration failed!")

    try:
        # Replace run_migrations with failing version
        init_module.run_migrations = failing_migrations

        with pytest.raises(sqlite3.OperationalError):
            init_db(conn)

        # Connection should still be usable after rollback
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

    finally:
        # Restore original function
        init_module.run_migrations = original_run_migrations

    conn.close()


def test_schema_has_required_tables():
    """Test that schema creates all expected tables"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    init_db(conn)

    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    tables = {row[0] for row in cursor.fetchall()}

    # Check some critical tables exist
    expected_tables = {
        "schema_migrations",
        "players",
        "player_skills",
        "teams",
        "leagues",
        "seasons",
        "games",
        "player_game_stats",
        "team_game_stats",
    }

    assert expected_tables.issubset(
        tables
    ), f"Missing tables: {expected_tables - tables}"

    conn.close()


def test_verify_schema_fails_on_missing_tables():
    """Test that verify_schema raises error when tables are missing"""
    conn = sqlite3.connect(":memory:")

    # Don't initialize - no tables exist
    with pytest.raises(RuntimeError, match="Missing required tables"):
        verify_schema(conn)

    conn.close()


def test_verify_schema_passes_after_init():
    """Test that verify_schema succeeds after initialization"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    init_db(conn)

    # Should not raise
    assert verify_schema(conn) is True

    conn.close()
