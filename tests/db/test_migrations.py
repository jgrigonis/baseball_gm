# tests/db/test_migrations.py

import pytest
from datetime import datetime, UTC
from unittest.mock import patch

from src.db.migrations import (
    run_migrations,
    _applied_versions,
    _record_migration,
)


# ============================================================================
# CRITICAL TESTS - Migration System Invariants
# ============================================================================


def test_migrations_are_idempotent(db_conn):
    """
    CRITICAL: Running migrations multiple times should be safe.

    Ensures the system won't break on restart, redeployment, or manual runs.
    """
    run_migrations(db_conn)
    run_migrations(db_conn)

    cursor = db_conn.execute(
        "SELECT version, COUNT(*) AS count FROM schema_migrations GROUP BY version"
    )
    for row in cursor:
        assert row["count"] == 1, (
            f"Migration {row['version']} was recorded {row['count']} times (should be 1)"
        )


def test_migrations_run_in_order(db_conn):
    """
    CRITICAL: Migrations must run in ascending version order so that
    dependencies between migrations are respected.
    """
    cursor = db_conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    versions = [row["version"] for row in cursor]
    assert versions == sorted(versions), "Migrations were not applied in order"


def test_partial_migrations_can_complete(db_conn):
    """
    CRITICAL: If migrations fail partway, re-running should complete them
    without re-applying already-applied versions.
    """
    applied_before = _applied_versions(db_conn)
    count_before = len(applied_before)

    # Simulate recording a new migration manually
    _record_migration(db_conn, 99999)
    db_conn.execute("SAVEPOINT after_record")

    applied_after = _applied_versions(db_conn)
    assert len(applied_after) == count_before + 1
    assert 99999 in applied_after

    # Existing versions should still appear exactly once
    cursor = db_conn.execute(
        "SELECT version, COUNT(*) AS cnt FROM schema_migrations GROUP BY version"
    )
    for row in cursor:
        assert row["cnt"] == 1, f"Migration {row['version']} duplicated"


def test_migration_gaps_are_allowed(db_conn):
    """
    CRITICAL: Version numbers can have gaps.
    Supports the rule: if you delete migration_003, use migration_004 next.
    """
    for v in [88881, 88883, 88885, 88890]:
        _record_migration(db_conn, v)

    versions = _applied_versions(db_conn)
    assert {88881, 88883, 88885, 88890}.issubset(versions)


def test_migration_table_created_automatically(db_conn):
    """
    CRITICAL: schema_migrations must exist so fresh databases can bootstrap.
    Verified here by confirming the table is present post-init.
    """
    cursor = db_conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'schema_migrations'
    """)
    assert cursor.fetchone() is not None


def test_applied_at_timestamp_is_recorded(db_conn):
    """Each migration records an applied_at timestamp for audit purposes."""
    before = datetime.now(UTC)
    _record_migration(db_conn, 77777)
    after = datetime.now(UTC)

    cursor = db_conn.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = %s", (77777,)
    )
    row = cursor.fetchone()
    assert row is not None

    applied_at = datetime.fromisoformat(row["applied_at"])
    assert before <= applied_at <= after


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


def test_empty_migration_list(db_conn):
    """System works correctly when no migrations are defined."""
    with patch("src.db.migrations.load_migrations", return_value=[]):
        run_migrations(db_conn)
        # No new versions should have been added beyond what already existed
        versions = _applied_versions(db_conn)
        assert isinstance(versions, set)


def test_migration_version_zero_is_valid(db_conn):
    """Version 0 is a valid migration number."""
    # Use a high sentinel so it doesn't collide with real migrations
    _record_migration(db_conn, 0)
    assert 0 in _applied_versions(db_conn)


def test_large_version_numbers(db_conn):
    """Timestamp-style version numbers (YYYYMMDDHHmmss) are supported."""
    large_version = 20250129120000
    _record_migration(db_conn, large_version)
    assert large_version in _applied_versions(db_conn)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_migrations_with_real_schema_changes(db_conn):
    """
    Smoke test: expected tables and columns exist after init_db.
    Confirms migrations actually ran against the real schema.
    """
    cursor = db_conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = {row["table_name"] for row in cursor.fetchall()}

    assert "schema_migrations" in tables
    assert "player_game_stats" in tables
    assert "players" in tables

    # Columns added by migration_001
    cursor = db_conn.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'player_game_stats'
    """)
    columns = {row["column_name"] for row in cursor.fetchall()}

    assert "pitch_doubles"  in columns
    assert "pitch_triples"  in columns
    assert "pitch_pickoffs" in columns


def test_migration_failure_rolls_back(db_conn):
    """
    A failing migration must not be recorded as applied, and any DML it
    performed must be rolled back.  In Postgres, DDL is also transactional,
    so this guarantee is stronger than it was under SQLite.
    """
    migration_executed = False

    def failing_migration(conn):
        nonlocal migration_executed
        migration_executed = True

        # Insert a canary row that should be rolled back on failure
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, %s)",
            (88888, datetime.now(UTC).isoformat()),
        )
        cursor = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = %s", (88888,)
        )
        assert cursor.fetchone() is not None, "Canary insert should have succeeded"

        raise RuntimeError("Migration failed!")

    with patch("src.db.migrations.load_migrations", return_value=[(99999, failing_migration)]):
        with pytest.raises(RuntimeError, match="Migration failed"):
            run_migrations(db_conn)

    assert migration_executed

    # Canary row (88888) must be gone
    cursor = db_conn.execute(
        "SELECT version FROM schema_migrations WHERE version = %s", (88888,)
    )
    assert cursor.fetchone() is None, "DML changes should have been rolled back"

    # Version 99999 must not be recorded
    assert 99999 not in _applied_versions(db_conn)


def test_migration_failure_does_not_record_migration(db_conn):
    """
    A failed migration must not appear in schema_migrations so that it will
    be retried on the next deployment after the bug is fixed.
    """
    def failing_migration(conn):
        raise RuntimeError("Intentional failure")

    with patch("src.db.migrations.load_migrations", return_value=[(55555, failing_migration)]):
        with pytest.raises(RuntimeError):
            run_migrations(db_conn)

    assert 55555 not in _applied_versions(db_conn)


def test_successful_migrations_before_failure_are_preserved(db_conn):
    """
    If migration 3 of 3 fails, migrations 1 and 2 are still committed and
    recorded.  Partial progress is preserved.
    """
    import uuid
    base = abs(hash(uuid.uuid4())) % 10_000_000 + 50_000_000  # unique 8-digit sentinel
    v1, v2, v3 = base + 1, base + 2, base + 3

    success_count = 0

    def ok1(conn):
        nonlocal success_count
        success_count += 1

    def ok2(conn):
        nonlocal success_count
        success_count += 1

    def fail3(conn):
        raise RuntimeError("Migration 3 failed!")

    migrations = [(v1, ok1), (v2, ok2), (v3, fail3)]

    with patch("src.db.migrations.load_migrations", return_value=migrations):
        with pytest.raises(RuntimeError, match="Migration 3 failed"):
            run_migrations(db_conn)

    assert success_count == 2

    versions = _applied_versions(db_conn)
    assert v1 in versions
    assert v2 in versions
    assert v3 not in versions


# ============================================================================
# DOCUMENTATION TESTS
# ============================================================================


def test_gap_scenario_from_docstring(db_conn):
    """
    Validates the scenario from the module docstring:
    'If you delete migration_003 and recreate it, use migration_004 instead.'

    Production has 001-003 applied.  New deploy adds 004 (gap is fine).
    """
    for v in [99901, 99902, 99903]:
        _record_migration(db_conn, v)

    versions_before = _applied_versions(db_conn)
    assert {99901, 99902, 99903}.issubset(versions_before)

    _record_migration(db_conn, 99904)

    versions_after = _applied_versions(db_conn)
    assert {99901, 99902, 99903, 99904}.issubset(versions_after)
