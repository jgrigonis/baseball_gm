# tests/db/test_init.py

import pytest
import psycopg
from unittest.mock import patch, Mock

from src.db.init import init_db, verify_schema


def test_init_db_creates_schema(db_conn):
    """Schema was created by the session fixture; verify it's valid."""
    assert verify_schema(db_conn)


def test_init_db_is_idempotent(db_conn):
    """init_db can be called multiple times safely (IF NOT EXISTS throughout)."""
    init_db(db_conn)
    init_db(db_conn)
    assert verify_schema(db_conn)


def test_init_db_rolls_back_on_error(db_conn):
    """init_db rolls back if migrations fail; connection remains usable after."""
    import src.db.init as init_module

    def failing_migrations(conn):
        raise psycopg.OperationalError("Migration failed!")

    with patch.object(init_module, "run_migrations", failing_migrations):
        with pytest.raises(psycopg.OperationalError):
            init_db(db_conn)

    # Connection should still be usable after the rollback
    cursor = db_conn.execute("SELECT 1 AS val")
    assert cursor.fetchone()["val"] == 1


def test_schema_has_required_tables(db_conn):
    """All expected tables exist after init_db."""
    cursor = db_conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = {row["table_name"] for row in cursor.fetchall()}

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
    assert expected_tables.issubset(tables), (
        f"Missing tables: {expected_tables - tables}"
    )


def test_verify_schema_fails_on_missing_tables():
    """verify_schema raises RuntimeError when required tables are absent."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = []
    mock_conn.execute.return_value = mock_cursor

    with pytest.raises(RuntimeError, match="Missing required tables"):
        verify_schema(mock_conn)


def test_verify_schema_passes_after_init(db_conn):
    """verify_schema returns True on a fully-initialised database."""
    assert verify_schema(db_conn) is True


def test_every_foreign_key_is_indexed(db_conn):
    """Deleting a row checks each table that references it, which scans the
    whole table unless an index starts with the referencing column. Leaving a
    league deletes its players, so one missing index made that take minutes."""
    unindexed = db_conn.execute("""
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f'
          AND c.connamespace = current_schema()::regnamespace
          AND NOT EXISTS (
              SELECT 1 FROM pg_index i
              WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
        """).fetchall()
    # The commissioner is one row per league; nothing deletes GMs in bulk.
    missing = [
        f"{r['tbl']}({r['col']})"
        for r in unindexed
        if (r["tbl"], r["col"]) != ("leagues", "commissioner_gm_id")
    ]
    assert missing == []


def test_init_db_upgrades_a_database_from_before_migration_36(db_conn):
    """On an existing database schema.py runs before the migrations, so it
    mustn't use a column a migration adds (e.g. index it): undo 036's
    column and init again, as on a database from before it."""
    db_conn.execute("ALTER TABLE all_stars DROP COLUMN replaces CASCADE")
    db_conn.execute("DELETE FROM schema_migrations WHERE version = 36")
    init_db(db_conn)
    row = db_conn.execute(
        """SELECT 1 FROM pg_indexes
           WHERE tablename = 'all_stars' AND indexname = 'idx_all_stars_replaces'"""
    ).fetchone()
    assert row
