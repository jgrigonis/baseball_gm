# tests/api/web/test_production_settings.py
"""
Settings that matter once the site is deployed, i.e. served over HTTPS as
PUBLIC_BASE_URL says: Secure cookies, no default admin password, and email
links that can't point anywhere but the site.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.config import settings
from src.db.migration_files import migration_010_admin

PASSWORD = "correct horse battery"


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _register(client):
    return client.post(
        "/auth/register",
        data={
            "username": "gm_" + uuid.uuid4().hex[:10],
            "password": PASSWORD,
            "confirm": PASSWORD,
        },
    )


class TestSessionCookie:
    def test_not_secure_while_developing(self, client):
        cookie = _register(client).headers["set-cookie"]

        assert "gm_session=" in cookie
        assert "secure" not in cookie.lower()

    def test_secure_when_served_over_https(self, client):
        with patch.object(settings, "public_base_url", "https://gm.example.com"):
            cookie = _register(client).headers["set-cookie"]

        assert "gm_session=" in cookie
        assert "; secure" in cookie.lower()

    def test_sign_out_clears_the_secure_cookie(self, client):
        with patch.object(settings, "public_base_url", "https://gm.example.com"):
            _register(client)
            cookie = client.post("/auth/logout").headers["set-cookie"]

        assert "; secure" in cookie.lower()


class TestDefaultAdmin:
    """Migration 010 makes the "admin" login on a fresh database."""

    @pytest.fixture
    def fresh(self, db_conn):
        db_conn.execute("DELETE FROM users WHERE lower(username) = 'admin'")
        return db_conn

    def _admin(self, db):
        return db.execute(
            "SELECT is_admin FROM users WHERE username = 'admin'"
        ).fetchone()

    def test_default_password_refused_when_deployed(self, fresh):
        with patch.object(settings, "public_base_url", "https://gm.example.com"):
            with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
                migration_010_admin.upgrade(fresh)

    def test_empty_password_refused(self, fresh):
        with patch.object(settings, "admin_initial_password", ""):
            with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
                migration_010_admin.upgrade(fresh)

    def test_chosen_password_is_fine_when_deployed(self, fresh):
        with (
            patch.object(settings, "public_base_url", "https://gm.example.com"),
            patch.object(settings, "admin_initial_password", "a long secret"),
        ):
            migration_010_admin.upgrade(fresh)

        assert self._admin(fresh)["is_admin"]

    def test_default_password_allowed_while_developing(self, fresh):
        migration_010_admin.upgrade(fresh)

        assert self._admin(fresh)["is_admin"]


def test_server_refuses_to_start_with_smtp_but_no_public_url():
    with (
        patch.object(settings, "smtp_host", "smtp.example.com"),
        patch.object(settings, "public_base_url", ""),
        patch("src.api.main.get_connection", return_value=Mock()),
        patch("src.api.main.pending_migrations", return_value=[]),
    ):
        with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
            with TestClient(app):
                pass
