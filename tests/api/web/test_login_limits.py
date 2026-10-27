# tests/api/web/test_login_limits.py
"""
Rate limits on signing in and on asking for password reset emails.

Routes run against the real test database and commit, so every test uses
fresh random usernames and IPs.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.api.services import login_limits, mailer, password_reset

PASSWORD = "correct horse battery"
WRONG = "not the password"
BLOCKED_TEXT = "Too many sign-in attempts."


def _name():
    return "gm_" + uuid.uuid4().hex[:10]


def _ip():
    n = uuid.uuid4().int
    return f"10.{n % 250}.{(n >> 8) % 250}.{(n >> 16) % 250}"


@pytest.fixture
def make_client(db_conn):
    """Clients from different IPs, sharing the test's database."""
    app.dependency_overrides[get_db] = lambda: db_conn
    yield lambda ip=None: TestClient(
        app, follow_redirects=False, client=(ip or _ip(), 50000)
    )
    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        mailer, "send", lambda to, subject, text: sent.append((to, subject, text))
    )
    return sent


def _account(client, email=None):
    name = _name()
    data = {"username": name, "password": PASSWORD, "confirm": PASSWORD}
    if email:
        data["email"] = f"{name}@example.com"
    assert client.post("/auth/register", data=data).status_code == 302
    client.post("/auth/logout")
    client.cookies.clear()
    return name


def _login(client, username, password=PASSWORD):
    return client.post("/auth/login", data={"username": username, "password": password})


def _fail(client, username, times):
    for _ in range(times):
        assert _login(client, username, WRONG).status_code == 401


class TestPerAccount:
    def test_locks_account_even_for_right_password(self, client):
        name = _account(client)
        _fail(client, name, login_limits.MAX_PER_ACCOUNT)

        r = _login(client, name)
        assert r.status_code == 429
        assert BLOCKED_TEXT in r.text
        assert "Try again in 15 minutes, or reset your password." in r.text
        assert "gm_session" not in r.cookies

    def test_lock_follows_account_across_ips_and_case(self, make_client):
        first = make_client()
        name = _account(first)
        _fail(first, name, login_limits.MAX_PER_ACCOUNT)
        assert _login(make_client(), name.upper()).status_code == 429

    def test_unknown_username_locks_the_same_way(self, client):
        name = _name()
        _fail(client, name, login_limits.MAX_PER_ACCOUNT)
        r = _login(client, name)
        assert r.status_code == 429
        assert BLOCKED_TEXT in r.text

    def test_other_accounts_still_sign_in(self, client):
        locked, other = _account(client), _account(client)
        _fail(client, locked, login_limits.MAX_PER_ACCOUNT)
        assert _login(client, other).status_code == 302

    def test_signing_in_clears_failures(self, client):
        name = _account(client)
        _fail(client, name, login_limits.MAX_PER_ACCOUNT - 1)
        assert _login(client, name).status_code == 302
        client.cookies.clear()
        _fail(client, name, login_limits.MAX_PER_ACCOUNT - 1)
        assert _login(client, name).status_code == 302

    def test_lock_lifts_after_window(self, client, db_conn):
        name = _account(client)
        _fail(client, name, login_limits.MAX_PER_ACCOUNT)
        db_conn.execute(
            "UPDATE login_failures SET created_at = created_at - make_interval(mins => %s) "
            "WHERE username = %s",
            (login_limits.WINDOW_MINUTES, name.lower()),
        )
        assert _login(client, name).status_code == 302

    def test_wait_counts_down_from_oldest_failure(self, client, db_conn):
        name = _account(client)
        _fail(client, name, login_limits.MAX_PER_ACCOUNT)
        db_conn.execute(
            "UPDATE login_failures SET created_at = created_at - interval '14 minutes' "
            "WHERE username = %s",
            (name.lower(),),
        )
        assert "Try again in 1 minute," in _login(client, name).text


class TestPerIP:
    def test_blocks_ip_guessing_many_accounts(self, make_client):
        ip = _ip()
        guesser = make_client(ip)
        for _ in range(login_limits.MAX_PER_IP):
            assert _login(guesser, _name(), WRONG).status_code == 401

        r = _login(guesser, _name())
        assert r.status_code == 429
        assert BLOCKED_TEXT in r.text
        # Other visitors aren't affected.
        other = make_client()
        assert _login(other, _account(other)).status_code == 302


class TestForgotPerIP:
    def test_limits_emails_from_one_ip(self, make_client, outbox):
        asker = make_client()
        names = [
            _account(asker, email=True)
            for _ in range(password_reset.MAX_PER_IP_PER_HOUR + 1)
        ]
        for name in names:
            r = asker.post("/auth/forgot", data={"login": name})
            assert r.status_code == 200
            assert "If that account has an email on file" in r.text
        assert len(outbox) == password_reset.MAX_PER_IP_PER_HOUR

        # The last account can still get its email from somewhere else.
        make_client().post("/auth/forgot", data={"login": names[-1]})
        assert len(outbox) == password_reset.MAX_PER_IP_PER_HOUR + 1
