# tests/api/test_profile_edit.py
"""Edit profile: a bio and favorite team on your GM profile (routers/profiles.py)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app


@pytest.fixture
def josh(db_conn):
    uid = str(uuid.uuid4())
    name = f"josh-{uid[:8]}"
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'Josh', %s)",
        (uid, uid, name),
    )
    return {"id": uid, "username": name, "has_password": False}


@pytest.fixture
def client(db_conn, josh):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: josh
    yield TestClient(app)
    app.dependency_overrides.clear()


def _row(db, uid):
    return db.execute(
        "SELECT bio, favorite_team FROM users WHERE id = %s", (uid,)
    ).fetchone()


def test_save_shows_on_the_profile(client, db_conn, josh):
    r = client.post(
        "/profile/edit",
        data={
            "bio": "  Build from the\nmound out.  ",
            "favorite_team_city": "Hong Kong",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/gms/{josh['username']}"
    assert dict(_row(db_conn, josh["id"])) == {
        "bio": "Build from the mound out.",
        "favorite_team": "Hong Kong",
    }
    html = client.get(f"/gms/{josh['username']}").text
    assert "Build from the mound out." in html
    assert "Favorite team <b>Hong Kong Harbor Kings</b>" in html
    assert 'href="/profile/edit"' in html


def test_form_shows_what_is_saved(client, db_conn, josh):
    db_conn.execute(
        "UPDATE users SET bio = 'Hi', favorite_team = 'Paris' WHERE id = %s",
        (josh["id"],),
    )
    html = client.get("/profile/edit").text
    assert 'value="Hi"' in html
    assert '<option value="Paris" selected>' in html


def test_clearing_both(client, db_conn, josh):
    db_conn.execute(
        "UPDATE users SET bio = 'Hi', favorite_team = 'Paris' WHERE id = %s",
        (josh["id"],),
    )
    client.post("/profile/edit", data={"bio": " ", "favorite_team_city": ""})
    assert dict(_row(db_conn, josh["id"])) == {"bio": None, "favorite_team": None}


def test_too_long_or_unknown_team_is_refused(client, db_conn, josh):
    r = client.post("/profile/edit", data={"bio": "x" * 161})
    assert r.status_code == 400 and "160 characters" in r.text
    r = client.post("/profile/edit", data={"favorite_team_city": "Atlantis"})
    assert r.status_code == 400 and "Pick a team" in r.text
    assert dict(_row(db_conn, josh["id"])) == {"bio": None, "favorite_team": None}


def test_other_profiles_have_no_edit_button(client, db_conn):
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'Sam', %s)",
        (uid, uid, f"sam-{uid[:8]}"),
    )
    html = client.get(f"/gms/sam-{uid[:8]}").text
    assert "/profile/edit" not in html


def test_no_username_no_profile_to_edit(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": "g", "username": None}
    try:
        r = TestClient(app).get("/profile/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 302
