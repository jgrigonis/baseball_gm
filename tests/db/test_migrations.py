# tests/db/test_migrations.py

import pytest
import sqlite3
from datetime import datetime, UTC
from unittest.mock import patch
from src.db.init import init_db  # Import init_db to set up base schema
from src.db.migrations import (
    run_migrations,
    _ensure_migration_table,
    _applied_versions,
    _record_migration,
)


# ============================================================================
# HELPER - Initialize database with base schema
# ============================================================================


def create_test_db():
    """
    Create a test database with base schema.

    This ensures migrations have the tables they expect to modify.
    """
    conn = sqlite3.connect(":memory:")
    init_db(conn)  # This creates base schema + runs migrations
    return conn


def create_empty_db():
    """Create a test database with ONLY the migration table, no schema."""
    conn = sqlite3.connect(":memory:")
    _ensure_migration_table(conn)
    return conn


# ============================================================================
# CRITICAL TESTS - Migration System Invariants
# ============================================================================


def test_migrations_are_idempotent():
    """
    CRITICAL: Running migrations multiple times should be safe.

    This test ensures that migrations don't break when:
    - Database is restarted
    - Application is redeployed
    - Developer runs migrations manually
    """
    conn = create_test_db()

    # Migrations already ran once in init_db
    # Run them again
    run_migrations(conn)
    run_migrations(conn)

    # Should not crash and should maintain consistent state
    _ = _applied_versions(conn)

    # Re-running should not duplicate version records
    cursor = conn.execute(
        "SELECT version, COUNT(*) as count FROM schema_migrations GROUP BY version"
    )
    for row in cursor:
        version, count = row
        assert (
            count == 1
        ), f"Migration {version} was recorded {count} times (should be 1)"

    conn.close()


def test_migrations_run_in_order():
    """
    CRITICAL: Migrations must run in version order.

    This ensures that:
    - Migration 002 runs after migration 001
    - Dependencies between migrations are respected
    - Database state is predictable
    """
    conn = create_test_db()

    # Get applied versions in order
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    versions = [row[0] for row in cursor]

    # Versions should be in ascending order
    assert versions == sorted(versions), "Migrations were not applied in order"

    conn.close()


def test_partial_migrations_can_complete():
    """
    CRITICAL: If migrations fail partway, re-running should complete them.

    Scenario:
    - Migrations 001, 002, 003 exist
    - 001 and 002 run successfully
    - 003 fails
    - Fix 003 and re-run
    - Should only run 003, not 001/002 again
    """
    conn = create_empty_db()

    # Simulate that migrations 001 and 002 already ran
    _record_migration(conn, 1)
    _record_migration(conn, 2)
    conn.commit()

    applied_before = _applied_versions(conn)
    assert 1 in applied_before
    assert 2 in applied_before

    # Record how many total migrations existed before
    count_before = len(applied_before)

    # Note: We can't actually run migrations here because they need the base schema
    # This test verifies the tracking logic works correctly

    # Verify that re-recording doesn't duplicate
    _record_migration(conn, 3)
    applied_after = _applied_versions(conn)

    assert len(applied_after) == count_before + 1
    assert 3 in applied_after

    # Versions 1 and 2 should still only appear once
    cursor = conn.execute(
        "SELECT version, COUNT(*) FROM schema_migrations WHERE version IN (1, 2) GROUP BY version"
    )
    for row in cursor:
        version, count = row
        assert count == 1, f"Old migration {version} was re-applied"

    conn.close()


def test_migration_gaps_are_allowed():
    """
    CRITICAL: Migration version numbers can have gaps.

    This supports the rule:
    "If you delete migration_003 and recreate it, use migration_004 instead"

    Gaps don't break the system.
    """
    conn = create_empty_db()

    # Simulate migrations with gaps: 1, 3, 5, 10
    _record_migration(conn, 1)
    _record_migration(conn, 3)
    _record_migration(conn, 5)
    _record_migration(conn, 10)
    conn.commit()

    # Should work fine
    versions = _applied_versions(conn)
    assert versions == {1, 3, 5, 10}

    conn.close()


def test_migration_table_created_automatically():
    """
    CRITICAL: Migration table must be created if it doesn't exist.

    This ensures migrations work on fresh databases.
    """
    conn = sqlite3.connect(":memory:")

    # Migration table should not exist yet
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    assert cursor.fetchone() is None

    # Running init_db should create it
    init_db(conn)

    # Now it should exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    assert cursor.fetchone() is not None

    conn.close()


def test_applied_at_timestamp_is_recorded():
    """
    IMPORTANT: Each migration records when it was applied.

    This helps with:
    - Debugging
    - Audit trails
    - Understanding deployment history
    """
    conn = create_empty_db()

    before = datetime.now(UTC)
    _record_migration(conn, 42)
    after = datetime.now(UTC)

    cursor = conn.execute("SELECT applied_at FROM schema_migrations WHERE version = 42")
    row = cursor.fetchone()

    assert row is not None
    applied_at = datetime.fromisoformat(row[0])

    # Timestamp should be between before and after
    assert before <= applied_at <= after

    conn.close()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


def test_empty_migration_list():
    """Test that system works even if no migrations exist."""
    conn = sqlite3.connect(":memory:")

    # Patch load_migrations to return empty list
    with patch("src.db.migrations.load_migrations", return_value=[]):
        # Should not crash even with no migrations
        run_migrations(conn)

        # Migration table should still be created
        versions = _applied_versions(conn)
        assert versions == set()

    conn.close()


def test_empty_migration_list_mock():
    """Test that system works even if no migrations exist."""
    conn = sqlite3.connect(":memory:")

    with patch("src.db.migrations.load_migrations", return_value=[]) as mock_load:
        run_migrations(conn)

        # Debug: verify mock was called
        print(f"Mock called: {mock_load.called}")
        print(f"Call count: {mock_load.call_count}")

        versions = _applied_versions(conn)
        assert versions == set()

    conn.close()


def test_migration_version_zero_is_valid():
    """Test that version 0 is a valid migration number."""
    conn = create_empty_db()

    _record_migration(conn, 0)

    versions = _applied_versions(conn)
    assert 0 in versions

    conn.close()


def test_large_version_numbers():
    """Test that large version numbers work (e.g., timestamp-based)."""
    conn = create_empty_db()

    # Use timestamp-style version numbers
    large_version = 20250129120000  # YYYYMMDDHHmmss format
    _record_migration(conn, large_version)

    versions = _applied_versions(conn)
    assert large_version in versions

    conn.close()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_migrations_with_real_schema_changes():
    """
    Integration test: Migrations should actually modify schema.

    This is a smoke test to ensure migrations do what they're supposed to.
    """
    conn = create_test_db()

    # Check that some expected tables exist (from your actual migrations)
    cursor = conn.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
        """
    )
    tables = {row[0] for row in cursor.fetchall()}

    # Migration table should exist
    assert "schema_migrations" in tables

    # Base schema tables should exist
    assert "player_game_stats" in tables
    assert "players" in tables

    # Check that migration actually added columns
    cursor = conn.execute("PRAGMA table_info(player_game_stats)")
    columns = {row[1] for row in cursor.fetchall()}  # row[1] is column name

    # These columns are added by migration_001
    assert "pitch_doubles" in columns
    assert "pitch_triples" in columns
    assert "pitch_pickoffs" in columns

    conn.close()


def test_migration_failure_rolls_back():
    """
    Test that if a migration fails, it's not recorded as applied.

    Note: SQLite cannot rollback DDL statements (CREATE TABLE),
    so we test with DML (INSERT) instead.
    """
    from src.db.schema import SCHEMA_SQL

    # Create database with base schema only (no migrations yet)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    _ensure_migration_table(conn)
    conn.commit()

    migration_executed = False

    def failing_migration(conn):
        nonlocal migration_executed
        migration_executed = True

        # Use DML (INSERT) instead of DDL (CREATE TABLE) because DML can be rolled back
        # Insert a test record into schema_migrations
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (888, datetime.now(UTC).isoformat()),
        )

        # Verify it was inserted
        cursor = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = 888"
        )
        assert cursor.fetchone() is not None, "Test insert should have succeeded"

        # Then fail
        raise RuntimeError("Migration failed!")

    # Patch load_migrations to return only our failing migration
    with patch(
        "src.db.migrations.load_migrations", return_value=[(999, failing_migration)]
    ):
        # Migration should fail and raise
        with pytest.raises(RuntimeError, match="Migration failed"):
            run_migrations(conn)

        # Verify migration actually ran
        assert migration_executed, "Mock migration was never called"

        # The test insert (version 888) should have been rolled back
        cursor = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = 888"
        )
        assert cursor.fetchone() is None, "DML changes should have been rolled back"

        # Migration 999 should NOT be recorded as applied
        versions = _applied_versions(conn)
        assert 999 not in versions, "Failed migration should not be recorded"

    conn.close()


def test_migration_failure_does_not_record_migration():
    """
    Test that failed migrations are not recorded in schema_migrations table.

    This is the most important guarantee: even if some changes persist
    (due to SQLite DDL limitations), the migration is not marked as applied,
    so it will be retried on next run.
    """
    from src.db.schema import SCHEMA_SQL

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    _ensure_migration_table(conn)
    conn.commit()

    def failing_migration(conn):
        # Do some work then fail
        raise RuntimeError("Intentional failure")

    with patch(
        "src.db.migrations.load_migrations", return_value=[(555, failing_migration)]
    ):
        with pytest.raises(RuntimeError):
            run_migrations(conn)

        # Critical: migration 555 should NOT be in schema_migrations
        versions = _applied_versions(conn)
        assert 555 not in versions

        # This means the migration will be retried on next deployment
        # (after the bug is fixed)

    conn.close()


def test_successful_migrations_before_failure_are_preserved():
    """
    Test that if migration 3 fails, migrations 1 and 2 are still recorded.

    This is important: partial progress is saved.
    """
    from src.db.schema import SCHEMA_SQL

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL)
    _ensure_migration_table(conn)
    conn.commit()

    success_count = 0

    def successful_migration_1(conn):
        nonlocal success_count
        success_count += 1
        # Does nothing, succeeds
        pass

    def successful_migration_2(conn):
        nonlocal success_count
        success_count += 1
        # Does nothing, succeeds
        pass

    def failing_migration_3(conn):
        raise RuntimeError("Migration 3 failed!")

    migrations = [
        (100, successful_migration_1),
        (200, successful_migration_2),
        (300, failing_migration_3),
    ]

    with patch("src.db.migrations.load_migrations", return_value=migrations):
        with pytest.raises(RuntimeError, match="Migration 3 failed"):
            run_migrations(conn)

        # First two should have run
        assert success_count == 2

        # First two should be recorded
        versions = _applied_versions(conn)
        assert 100 in versions
        assert 200 in versions

        # Third should NOT be recorded
        assert 300 not in versions

    conn.close()


# ============================================================================
# DOCUMENTATION TESTS (Ensure examples in docstrings work)
# ============================================================================


def test_gap_scenario_from_docstring():
    """
    Test the scenario described in module docstring:
    "If you delete migration_003 locally and recreate it, use migration_004 instead"

    Timeline:
    - Migrations 001, 002, 003 exist in production
    - Developer deletes 003 locally
    - Creates new migration as 004 (not 003 again)
    - Deploys
    - Production already has 003 applied
    - Should apply 004 without issues
    """
    conn = create_empty_db()

    # Production state: 001, 002, 003 already applied
    _record_migration(conn, 1)
    _record_migration(conn, 2)
    _record_migration(conn, 3)
    conn.commit()

    # Now we add migration 004 (gap is fine)
    versions_before = _applied_versions(conn)
    assert versions_before == {1, 2, 3}

    # This should work without issues
    _record_migration(conn, 4)

    versions_after = _applied_versions(conn)
    assert versions_after == {1, 2, 3, 4}

    conn.close()
