# tests/api/web/test_auth.py
"""
Password logins: creating an account, signing in and out, and moving guests
from before passwords existed onto a username and password.

Routes run against the real test database. They commit, so every test uses
fresh random usernames.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.main import app
from src.db.repositories.user_repo import UserRepository

PASSWORD = "correct horse battery"


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


def _register(client, username, password=PASSWORD, confirm=None, email=None):
    data = {
        "username": username,
        "password": password,
        "confirm": PASSWORD if confirm is None else confirm,
    }
    if email is not None:
        data["email"] = email
    return client.post("/auth/register", data=data)


def _login(client, username, password=PASSWORD):
    return client.post("/auth/login", data={"username": username, "password": password})


def _bounced_to_landing(r):
    """Routes needing a user answer an unknown session by going to /."""
    return r.status_code == 307 and r.headers["location"] == "/"


def _legacy_guest(db_conn, display_name):
    """A users row as the old guest flow made it: no username or password."""
    user_id, token = str(uuid.uuid4()), uuid.uuid4().hex
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
        (user_id, token, display_name),
    )
    return user_id, token


class TestPages:
    def test_landing_is_sign_in_and_links_to_sign_up(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert 'action="/auth/login"' in r.text
        assert 'action="/auth/register"' not in r.text
        assert 'href="/signup"' in r.text

    def test_signup_page_links_back_to_sign_in(self, client):
        r = client.get("/signup")
        assert r.status_code == 200
        assert 'action="/auth/register"' in r.text
        assert 'action="/auth/login"' not in r.text
        assert 'name="email"' in r.text
        assert 'href="/"' in r.text

    def test_signed_in_users_skip_signup(self, client):
        _register(client, _name())
        r = client.get("/signup")
        assert r.status_code == 307
        assert r.headers["location"] == "/leagues/"


class TestRegister:
    def test_creates_user_and_signs_in(self, client, db_conn):
        name = _name()
        r = _register(client, name)

        assert r.status_code == 302
        assert r.headers["location"] == "/leagues/"
        row = db_conn.execute(
            "SELECT display_name, password_hash, session_token FROM users "
            "WHERE username = %s",
            (name,),
        ).fetchone()
        assert row["display_name"] == name
        assert row["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in row["password_hash"]
        assert client.cookies["gm_session"] == row["session_token"]

    def test_email_is_optional(self, client, db_conn):
        name = _name()
        assert _register(client, name, email="").status_code == 302
        row = db_conn.execute(
            "SELECT email FROM users WHERE username = %s", (name,)
        ).fetchone()
        assert row["email"] is None

    def test_stores_email(self, client, db_conn):
        name = _name()
        email = f"{name}@example.com"
        assert _register(client, name, email=f"  {email} ").status_code == 302
        row = db_conn.execute(
            "SELECT email FROM users WHERE username = %s", (name,)
        ).fetchone()
        assert row["email"] == email

    def test_rejects_bad_email(self, client):
        r = _register(client, _name(), email="not-an-email")
        assert r.status_code == 400
        assert "email address" in r.text
        assert "gm_session" not in r.cookies

    def test_email_taken_ignoring_case(self, client):
        email = f"{_name()}@example.com"
        assert _register(client, _name(), email=email).status_code == 302
        client.cookies.clear()

        r = _register(client, _name(), email=email.upper())
        assert r.status_code == 400
        assert "has that email" in r.text
        assert 'href="/"' in r.text

    def test_username_taken_ignoring_case(self, client):
        name = _name()
        assert _register(client, name).status_code == 302
        client.cookies.clear()

        r = _register(client, name.upper())
        assert r.status_code == 400
        assert "taken" in r.text

    @pytest.mark.parametrize(
        "username, password, confirm",
        [
            ("ab", PASSWORD, PASSWORD),
            ("has space", PASSWORD, PASSWORD),
            ("x" * 31, PASSWORD, PASSWORD),
            ("okname", "short", "short"),
            ("okname", PASSWORD, PASSWORD + "!"),
        ],
    )
    def test_rejects_bad_input(self, client, db_conn, username, password, confirm):
        r = _register(client, username, password, confirm)
        assert r.status_code == 400
        assert "gm_session" not in r.cookies


class TestLogin:
    def test_right_password_signs_in(self, client, db_conn):
        name = _name()
        _register(client, name)
        client.cookies.clear()

        r = _login(client, name.upper())
        assert r.status_code == 302
        token = db_conn.execute(
            "SELECT session_token FROM users WHERE username = %s", (name,)
        ).fetchone()["session_token"]
        assert client.cookies["gm_session"] == token
        assert client.get("/leagues/").status_code == 200

    def test_wrong_password_and_unknown_user_look_the_same(self, client):
        name = _name()
        _register(client, name)
        client.cookies.clear()

        wrong = _login(client, name, "not the password")
        unknown = _login(client, _name())
        for r in (wrong, unknown):
            assert r.status_code == 401
            assert "Wrong username or password." in r.text
            assert "gm_session" not in r.cookies

    def test_passwordless_guest_cannot_sign_in(self, client, db_conn):
        name = _name()
        _legacy_guest(db_conn, name)
        assert _login(client, name).status_code == 401

    def test_logout_ends_session_and_login_restores_it(self, client):
        name = _name()
        _register(client, name)
        old = client.cookies["gm_session"]

        client.post("/auth/logout")
        client.cookies.set("gm_session", old)
        assert _bounced_to_landing(client.get("/leagues/"))

        client.cookies.clear()
        _login(client, name)
        assert client.get("/leagues/").status_code == 200


class TestLegacyGuests:
    def test_sent_to_set_password(self, client, db_conn):
        _, token = _legacy_guest(db_conn, "Old Guest")
        client.cookies.set("gm_session", token)

        r = client.get("/leagues/")
        assert r.status_code == 302
        assert r.headers["location"] == "/auth/set-password"
        assert client.get("/auth/set-password").status_code == 200

    def test_set_password_keeps_user_and_rotates_token(self, client, db_conn):
        user_id, old_token = _legacy_guest(db_conn, "Old Guest")
        client.cookies.set("gm_session", old_token)
        name = _name()

        r = client.post(
            "/auth/set-password",
            data={"username": name, "password": PASSWORD, "confirm": PASSWORD},
        )
        assert r.status_code == 302
        new_token = r.cookies["gm_session"]
        assert new_token != old_token

        repo = UserRepository(db_conn)
        assert repo.get_by_token(old_token) is None
        user = repo.get_by_token(new_token)
        assert user["id"] == user_id
        assert user["username"] == name
        assert user["display_name"] == "Old Guest"
        assert user["has_password"]

        client.cookies.clear()
        assert _login(client, name).status_code == 302

    def test_set_password_rejects_taken_username(self, client, db_conn):
        taken = _name()
        _register(client, taken)
        client.cookies.clear()

        _, token = _legacy_guest(db_conn, "Old Guest")
        client.cookies.set("gm_session", token)
        r = client.post(
            "/auth/set-password",
            data={"username": taken, "password": PASSWORD, "confirm": PASSWORD},
        )
        assert r.status_code == 400
        assert UserRepository(db_conn).get_by_token(token)["has_password"] is False

    def test_needs_a_session(self, client):
        assert _bounced_to_landing(client.get("/auth/set-password"))


def test_same_name_no_longer_takes_over_teams(client, db_conn, factory):
    """
    The old /leagues/ page moved every gm row whose user had the same
    display_name onto the current user. A new account with someone's name
    must not get their teams.
    """
    name = _name()
    victim_id, _ = _legacy_guest(db_conn, name)
    league = factory.league()
    gm_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name) VALUES (%s, %s, %s, %s)",
        (gm_id, league.id, victim_id, name),
    )

    _register(client, name)
    assert client.get("/leagues/").status_code == 200

    owner = db_conn.execute(
        "SELECT user_id FROM gms WHERE id = %s", (gm_id,)
    ).fetchone()["user_id"]
    assert owner == victim_id
