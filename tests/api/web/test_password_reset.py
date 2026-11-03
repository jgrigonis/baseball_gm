# tests/api/web/test_password_reset.py
"""
Forgotten passwords: emailing a reset link, using it, and the account page
where users add the email those links go to.

Routes run against the real test database and commit, so every test uses
fresh random usernames. Emails are captured instead of sent.
"""

import re
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.api.services import mailer, password_reset

PASSWORD = "correct horse battery"
NEW_PASSWORD = "a brand new password"
SENT_TEXT = "If that account has an email on file"


def _name():
    return "gm_" + uuid.uuid4().hex[:10]


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    # A fresh IP per test, so failures and emails committed by earlier tests
    # don't count toward the per-IP limits.
    ip = (
        f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    )
    yield TestClient(app, follow_redirects=False, client=(ip, 50000))
    app.dependency_overrides.clear()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        mailer, "send", lambda to, subject, text: sent.append((to, subject, text))
    )
    return sent


def _register(client, username, email=None):
    data = {"username": username, "password": PASSWORD, "confirm": PASSWORD}
    if email is not None:
        data["email"] = email
    r = client.post("/auth/register", data=data)
    assert r.status_code == 302
    return r


def _account(client, email=True):
    """A signed-out account; returns (username, email)."""
    name = _name()
    address = f"{name}@example.com" if email else None
    _register(client, name, address)
    client.post("/auth/logout")
    client.cookies.clear()
    return name, address


def _token(mail):
    link = re.search(r"(http\S+/auth/reset\?\S+)", mail[2]).group(1)
    return parse_qs(urlparse(link).query)["token"][0]


def _forgot(client, login):
    return client.post("/auth/forgot", data={"login": login})


def _reset(client, token, password=NEW_PASSWORD, confirm=None):
    return client.post(
        "/auth/reset",
        data={"token": token, "password": password, "confirm": confirm or password},
    )


def _login(client, username, password):
    return client.post("/auth/login", data={"username": username, "password": password})


class TestForgot:
    def test_landing_links_to_forgot(self, client):
        assert 'href="/auth/forgot"' in client.get("/").text

    def test_page(self, client):
        r = client.get("/auth/forgot")
        assert r.status_code == 200
        assert 'action="/auth/forgot"' in r.text

    @pytest.mark.parametrize("by_email", [False, True])
    def test_emails_a_link(self, client, db_conn, outbox, by_email):
        name, email = _account(client)
        r = _forgot(client, email.upper() if by_email else name.upper())

        assert r.status_code == 200
        assert SENT_TEXT in r.text
        assert len(outbox) == 1
        to, subject, text = outbox[0]
        assert to == email
        assert name in text
        token = _token(outbox[0])
        row = db_conn.execute(
            "SELECT token_hash, expires_at - created_at AS ttl FROM password_resets "
            "WHERE token_hash = %s",
            (password_reset.hash_token(token),),
        ).fetchone()
        assert row is not None
        assert token not in row["token_hash"]
        assert row["ttl"].total_seconds() == password_reset.RESET_TTL_MINUTES * 60

    def test_unknown_and_emailless_accounts_get_the_same_answer(self, client, outbox):
        name, _ = _account(client, email=False)
        for login in (name, _name(), "nobody@example.com"):
            r = _forgot(client, login)
            assert r.status_code == 200
            assert SENT_TEXT in r.text
            assert "Ask an admin" in r.text
        assert outbox == []

    def test_limits_emails_per_account(self, client, outbox):
        name, _ = _account(client)
        for _ in range(password_reset.MAX_PER_HOUR + 2):
            assert SENT_TEXT in _forgot(client, name).text
        assert len(outbox) == password_reset.MAX_PER_HOUR

    def test_new_link_replaces_old_one(self, client, outbox):
        name, _ = _account(client)
        _forgot(client, name)
        _forgot(client, name)
        old, new = _token(outbox[0]), _token(outbox[1])
        assert client.get(f"/auth/reset?token={old}").status_code == 400
        assert client.get(f"/auth/reset?token={new}").status_code == 200

    def test_needs_public_base_url_to_send_real_mail(self, client, outbox, monkeypatch):
        from src.config import settings

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "public_base_url", "")
        name, _ = _account(client)
        assert SENT_TEXT in _forgot(client, name).text
        assert outbox == []

        monkeypatch.setattr(settings, "public_base_url", "https://gm.example.com/")
        _forgot(client, name)
        assert "https://gm.example.com/auth/reset?token=" in outbox[0][2]


class TestReset:
    def _link(self, client, outbox):
        name, _ = _account(client)
        _forgot(client, name)
        return name, _token(outbox[-1])

    def test_sets_password_and_signs_in(self, client, db_conn, outbox):
        name, token = self._link(client, outbox)
        page = client.get(f"/auth/reset?token={token}")
        assert page.status_code == 200
        assert name in page.text

        r = _reset(client, token)
        assert r.status_code == 302
        assert r.headers["location"] == "/leagues/"
        row = db_conn.execute(
            "SELECT session_token, must_change_password FROM users WHERE username = %s",
            (name,),
        ).fetchone()
        assert client.cookies["gm_session"] == row["session_token"]
        assert row["must_change_password"] is False

        client.cookies.clear()
        assert _login(client, name, PASSWORD).status_code == 401
        assert _login(client, name, NEW_PASSWORD).status_code == 302

    def test_old_password_works_until_reset(self, client, outbox):
        name, _ = self._link(client, outbox)
        assert _login(client, name, PASSWORD).status_code == 302

    def test_signs_out_other_browsers(self, client, db_conn, outbox):
        name, _ = _account(client)
        _login(client, name, PASSWORD)
        old_session = client.cookies["gm_session"]
        _forgot(client, name)
        _reset(client, _token(outbox[-1]))
        client.cookies.clear()
        client.cookies.set("gm_session", old_session)
        assert client.get("/leagues/").status_code == 307

    def test_link_works_once(self, client, outbox):
        _, token = self._link(client, outbox)
        assert _reset(client, token).status_code == 302
        client.cookies.clear()
        r = _reset(client, token, "yet another password")
        assert r.status_code == 400
        assert "expired or was already used" in r.text
        assert client.get(f"/auth/reset?token={token}").status_code == 400

    def test_opening_the_link_does_not_use_it(self, client, outbox):
        _, token = self._link(client, outbox)
        client.get(f"/auth/reset?token={token}")
        client.get(f"/auth/reset?token={token}")
        assert _reset(client, token).status_code == 302

    def test_expired_link(self, client, db_conn, outbox):
        _, token = self._link(client, outbox)
        db_conn.execute(
            "UPDATE password_resets SET expires_at = NOW() - interval '1 minute' "
            "WHERE token_hash = %s",
            (password_reset.hash_token(token),),
        )
        assert client.get(f"/auth/reset?token={token}").status_code == 400
        assert _reset(client, token).status_code == 400

    @pytest.mark.parametrize("token", ["", "not-a-real-token"])
    def test_bad_token(self, client, token):
        r = client.get(f"/auth/reset?token={token}")
        assert r.status_code == 400
        assert 'href="/auth/forgot"' in r.text
        assert _reset(client, token).status_code == 400

    def test_bad_password_keeps_the_link(self, client, outbox):
        _, token = self._link(client, outbox)
        r = _reset(client, token, "short")
        assert r.status_code == 400
        assert "at least" in r.text
        r = _reset(client, token, NEW_PASSWORD, "different password")
        assert r.status_code == 400
        assert _reset(client, token).status_code == 302

    def test_changing_password_kills_pending_links(self, client, outbox):
        name, token = self._link(client, outbox)
        _login(client, name, PASSWORD)
        r = client.post(
            "/auth/change-password",
            data={
                "current": PASSWORD,
                "password": NEW_PASSWORD,
                "confirm": NEW_PASSWORD,
            },
        )
        assert r.status_code == 302
        assert client.get(f"/auth/reset?token={token}").status_code == 400

    def test_clears_must_change(self, client, db_conn, outbox):
        name, token = self._link(client, outbox)
        db_conn.execute(
            "UPDATE users SET must_change_password = TRUE WHERE username = %s", (name,)
        )
        _reset(client, token)
        assert client.get("/leagues/").status_code == 200


class TestAccount:
    def _signed_in(self, client, email=None):
        name = _name()
        _register(client, name, email)
        return name

    def test_needs_sign_in(self, client):
        r = client.get("/account")
        assert r.status_code == 307
        assert r.headers["location"] == "/"

    def test_page_and_nav_link(self, client):
        self._signed_in(client)
        r = client.get("/account")
        assert r.status_code == 200
        assert "no email on file" in r.text
        assert 'href="/account"' in client.get("/leagues/").text

    def test_add_email(self, client, db_conn, outbox):
        name = self._signed_in(client)
        email = f"{name}@example.com"
        r = client.post("/account/email", data={"current": PASSWORD, "email": email})
        assert r.status_code == 303
        assert r.headers["location"] == "/account?saved=email"
        assert (
            db_conn.execute(
                "SELECT email FROM users WHERE username = %s", (name,)
            ).fetchone()["email"]
            == email
        )

        client.cookies.clear()
        _forgot(client, name)
        assert outbox[0][0] == email

    def test_turn_emails_toggle(self, client, db_conn):
        name = self._signed_in(client)
        assert "Email me when it's my move" in client.get("/account").text

        def on():
            return db_conn.execute(
                "SELECT turn_emails FROM users WHERE username = %s", (name,)
            ).fetchone()["turn_emails"]

        assert on()
        r = client.post("/account/turn-emails", data={})
        assert r.status_code == 303
        assert not on()
        client.post("/account/turn-emails", data={"on": "1"})
        assert on()

    def test_clear_email(self, client, db_conn):
        name = self._signed_in(client, f"{_name()}@example.com")
        r = client.post("/account/email", data={"current": PASSWORD, "email": ""})
        assert r.status_code == 303
        assert (
            db_conn.execute(
                "SELECT email FROM users WHERE username = %s", (name,)
            ).fetchone()["email"]
            is None
        )

    def test_needs_current_password(self, client, db_conn):
        name = self._signed_in(client)
        r = client.post(
            "/account/email",
            data={"current": "wrong password", "email": "x@example.com"},
        )
        assert r.status_code == 400
        assert "current password is wrong" in r.text
        assert (
            db_conn.execute(
                "SELECT email FROM users WHERE username = %s", (name,)
            ).fetchone()["email"]
            is None
        )

    def test_rejects_taken_and_bad_email(self, client):
        other = f"{_name()}@example.com"
        self._signed_in(client, other)
        client.cookies.clear()
        self._signed_in(client)
        r = client.post(
            "/account/email", data={"current": PASSWORD, "email": other.upper()}
        )
        assert r.status_code == 400
        assert "Another account has that email" in r.text
        r = client.post("/account/email", data={"current": PASSWORD, "email": "nope"})
        assert r.status_code == 400
