"""
Verifying an email (src/api/services/email_verify.py): the link, the
Verified Email badge, and losing both when the email changes.

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
from src.api.services import badges, email_verify, mailer
from tests.api.web.test_password_reset import PASSWORD, _name, _register


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
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


def _token(mail):
    link = re.search(r"(http\S+/account/verify-email\?\S+)", mail[2]).group(1)
    return parse_qs(urlparse(link).query)["token"][0]


def _user(db, name):
    return db.execute(
        "SELECT id, email, is_verified FROM users WHERE username = %s", (name,)
    ).fetchone()


def _has_badge(db, name):
    return email_verify.BADGE in badges.earned(db, _user(db, name)["id"])


def _set_email(client, email):
    return client.post("/account/email", data={"current": PASSWORD, "email": email})


@pytest.fixture
def account(client):
    """Signed in, with an email that isn't verified yet. Returns the name."""
    name = _name()
    _register(client, name, f"{name}@example.com")
    return name


class TestVerify:
    def test_account_page_offers_a_link(self, client, account):
        text = client.get("/account").text
        assert "isn't verified yet" in text
        assert "Send Verification Link" in text

    def test_link_verifies_and_awards_badge(self, client, db_conn, outbox, account):
        r = client.post("/account/verify-email")
        assert r.status_code == 303
        assert r.headers["location"] == "/account?saved=verify_sent"
        assert outbox[-1][0] == f"{account}@example.com"
        assert not _user(db_conn, account)["is_verified"]

        r = client.get(f"/account/verify-email?token={_token(outbox[-1])}")
        assert r.status_code == 200
        assert "Email verified" in r.text
        assert _user(db_conn, account)["is_verified"]
        assert _has_badge(db_conn, account)
        assert "is verified" in client.get("/account").text

    def test_works_signed_out(self, client, db_conn, outbox, account):
        client.post("/account/verify-email")
        client.cookies.clear()
        r = client.get(f"/account/verify-email?token={_token(outbox[-1])}")
        assert r.status_code == 200
        assert _user(db_conn, account)["is_verified"]

    def test_link_works_once(self, client, outbox, account):
        client.post("/account/verify-email")
        token = _token(outbox[-1])
        assert client.get(f"/account/verify-email?token={token}").status_code == 200
        r = client.get(f"/account/verify-email?token={token}")
        assert r.status_code == 400
        assert "didn't work" in r.text

    def test_bad_token(self, client):
        assert client.get("/account/verify-email?token=nope").status_code == 400
        assert client.get("/account/verify-email").status_code == 400

    def test_new_link_replaces_old_one(self, client, db_conn, outbox, account):
        client.post("/account/verify-email")
        old = _token(outbox[-1])
        client.post("/account/verify-email")
        assert client.get(f"/account/verify-email?token={old}").status_code == 400
        assert not _user(db_conn, account)["is_verified"]

    def test_limits_emails_per_hour(self, client, outbox, account):
        for _ in range(email_verify.MAX_PER_HOUR):
            assert client.post("/account/verify-email").status_code == 303
        r = client.post("/account/verify-email")
        assert r.status_code == 400
        assert "Too many" in r.text
        assert len(outbox) == email_verify.MAX_PER_HOUR

    def test_no_email(self, client):
        _register(client, _name())
        # The page offers no button then; a hand-made POST is just refused.
        assert client.post("/account/verify-email").status_code == 400

    def test_needs_sign_in(self, client):
        assert client.post("/account/verify-email").status_code in (303, 307)


class TestChangingEmail:
    def _verify(self, client, outbox):
        client.post("/account/verify-email")
        client.get(f"/account/verify-email?token={_token(outbox[-1])}")

    def test_new_email_unverifies_and_takes_badge(
        self, client, db_conn, outbox, account
    ):
        self._verify(client, outbox)
        assert _has_badge(db_conn, account)

        new = f"{_name()}@example.com"
        r = _set_email(client, new)
        assert r.headers["location"] == "/account?saved=email_sent"
        user = _user(db_conn, account)
        assert user["email"] == new and not user["is_verified"]
        assert not _has_badge(db_conn, account)
        # The link for the new address came along with the change.
        assert outbox[-1][0] == new

        client.get(f"/account/verify-email?token={_token(outbox[-1])}")
        assert _user(db_conn, account)["is_verified"]
        assert _has_badge(db_conn, account)

    def test_old_link_cant_verify_new_email(self, client, db_conn, outbox, account):
        client.post("/account/verify-email")
        old = _token(outbox[-1])
        _set_email(client, f"{_name()}@example.com")
        assert client.get(f"/account/verify-email?token={old}").status_code == 400
        assert not _user(db_conn, account)["is_verified"]

    def test_same_email_in_other_case_stays_verified(
        self, client, db_conn, outbox, account
    ):
        self._verify(client, outbox)
        sent = len(outbox)
        r = _set_email(client, f"{account.upper()}@EXAMPLE.COM")
        assert r.headers["location"] == "/account?saved=email"
        assert _user(db_conn, account)["is_verified"]
        assert _has_badge(db_conn, account)
        assert len(outbox) == sent

    def test_clearing_email_unverifies(self, client, db_conn, outbox, account):
        self._verify(client, outbox)
        r = _set_email(client, "")
        assert r.headers["location"] == "/account?saved=email"
        assert not _user(db_conn, account)["is_verified"]
        assert not _has_badge(db_conn, account)
        assert "isn't verified" not in client.get("/account").text

    def test_admin_change_unverifies(self, client, db_conn, outbox, account):
        self._verify(client, outbox)
        user_id = _user(db_conn, account)["id"]
        from src.api.dependencies import get_admin

        app.dependency_overrides[get_admin] = lambda: {"id": "someone-else"}
        r = client.post(
            f"/admin/users/{user_id}/email",
            data={"email": f"{_name()}@example.com"},
        )
        assert r.status_code == 303
        assert not _user(db_conn, account)["is_verified"]
        assert not _has_badge(db_conn, account)
