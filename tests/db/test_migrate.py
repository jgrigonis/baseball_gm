# tests/db/test_migrate.py
#
# The separate migration step (src/db/migrate.py), and the web server's
# refusal to start while migrations are pending.

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

import src.db.migrations as migrations_module
from src.api.main import app
from src.db.migrate import migrate
from src.db.migrations import pending_migrations


_real_load_migrations = migrations_module.load_migrations


def _with_extra_migration():
    """load_migrations() plus a version the database hasn't seen."""
    return _real_load_migrations() + [(999_999, lambda conn: None)]


def _advisory_locks_held(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM pg_locks"
        " WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
    ).fetchone()["n"]


def test_nothing_pending_after_init(db_conn):
    assert pending_migrations(db_conn) == []


def test_new_migration_is_pending(db_conn):
    with patch.object(migrations_module, "load_migrations", _with_extra_migration):
        assert pending_migrations(db_conn) == [999_999]


def test_migrate_up_to_date_applies_nothing_and_releases_the_lock(db_conn):
    assert migrate(db_conn) == []
    assert _advisory_locks_held(db_conn) == 0


def test_migrate_releases_the_lock_when_a_migration_fails(db_conn):
    import src.db.init as init_module

    def failing(conn):
        raise RuntimeError("boom")

    with patch.object(init_module, "run_migrations", failing):
        with pytest.raises(RuntimeError):
            migrate(db_conn)
    assert _advisory_locks_held(db_conn) == 0


def test_server_refuses_to_start_with_pending_migrations():
    with (
        patch("src.api.main.get_connection", return_value=Mock()),
        patch("src.api.main.pending_migrations", return_value=[27, 28]),
    ):
        with pytest.raises(RuntimeError, match="src.db.migrate"):
            with TestClient(app):
                pass


def test_server_starts_when_up_to_date():
    with (
        patch("src.api.main.get_connection", return_value=Mock()),
        patch("src.api.main.pending_migrations", return_value=[]),
    ):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
