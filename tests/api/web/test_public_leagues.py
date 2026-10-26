# tests/api/web/test_public_leagues.py
"""
A league can be made public when it's created. Public leagues the user isn't
in show under Public Leagues on the leagues page. The ones still in the lobby
can be joined from there without a code, and the rest can be viewed.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app


def _league(db, name, state="lobby", is_public=True):
    league_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO leagues (id, name, state, is_public) VALUES (%s, %s, %s, %s)",
        (league_id, name, state, is_public),
    )
    return league_id


def _gm(db, league_id, user_id):
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name) VALUES (%s, %s, %s, 'GM')",
        (str(uuid.uuid4()), league_id, user_id),
    )


@pytest.fixture
def user_id(db_conn):
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username, password_hash)"
        " VALUES (%s, %s, 'Alice', %s, 'x')",
        (uid, uid, uid),
    )
    return uid


@pytest.fixture
def client(db_conn, user_id):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user_id,
        "has_password": True,
        "display_name": "Alice",
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _public_section(html):
    return html.split("Public Leagues</h1>")[1]


def test_lists_public_leagues_only(client, db_conn):
    _league(db_conn, "Open Lobby")
    _league(db_conn, "Secret League", is_public=False)

    section = _public_section(client.get("/leagues/").text)

    assert "Open Lobby" in section
    assert "Secret League" not in section


def test_leaves_out_leagues_the_user_is_in(client, db_conn, user_id):
    mine = _league(db_conn, "Already Mine")
    _gm(db_conn, mine, user_id)

    section = _public_section(client.get("/leagues/").text)

    assert "Already Mine" not in section


def test_lists_finished_leagues_last(client, db_conn):
    _league(db_conn, "All Done", state="complete")
    _league(db_conn, "In Season", state="season")

    section = _public_section(client.get("/leagues/").text)

    assert section.index("In Season") < section.index("All Done")


def test_only_lobby_leagues_can_be_joined(client, db_conn):
    lobby = _league(db_conn, "Open Lobby")
    started = _league(db_conn, "In Season", state="season")

    section = _public_section(client.get("/leagues/").text)

    assert f"/leagues/{lobby}/join" in section
    assert f"/leagues/{started}/join" not in section
    assert f'href="/leagues/{started}/"' in section


def test_joining_a_public_league(client, db_conn, user_id):
    league_id = _league(db_conn, "Open Lobby")

    r = client.post(f"/leagues/{league_id}/join")

    assert r.headers["location"] == f"/leagues/{league_id}/"
    gm = db_conn.execute(
        "SELECT 1 FROM gms WHERE league_id = %s AND user_id = %s", (league_id, user_id)
    ).fetchone()
    assert gm is not None


@pytest.mark.parametrize("state, is_public", [("lobby", False), ("season", True)])
def test_cant_join_private_or_started_leagues(
    client, db_conn, user_id, state, is_public
):
    league_id = _league(db_conn, "Closed", state=state, is_public=is_public)

    r = client.post(f"/leagues/{league_id}/join")

    assert r.headers["location"] == "/leagues/"
    gm = db_conn.execute(
        "SELECT 1 FROM gms WHERE league_id = %s AND user_id = %s", (league_id, user_id)
    ).fetchone()
    assert gm is None


@pytest.mark.parametrize("form, expected", [({}, False), ({"is_public": "true"}, True)])
def test_new_league_visibility(client, db_conn, form, expected):
    r = client.post("/leagues/new", data={"name": "Fresh League", **form})

    league_id = r.headers["location"].split("/")[2]
    row = db_conn.execute(
        "SELECT is_public FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    assert row["is_public"] is expected


def test_completed_leagues_show_by_default(client, db_conn):
    _league(db_conn, "All Done", state="complete")

    html = client.get("/leagues/").text

    assert "All Done" in _public_section(html)
    assert 'id="completed-toggle"' in html


def test_hiding_completed_leagues(client, db_conn, user_id):
    _league(db_conn, "All Done", state="complete")
    _league(db_conn, "In Season", state="season")
    mine = _league(db_conn, "My Old One", state="complete", is_public=False)
    _gm(db_conn, mine, user_id)

    r = client.get("/leagues/?completed=hide")

    assert "All Done" not in r.text
    assert "My Old One" not in r.text
    assert "In Season" in _public_section(r.text)
    assert "All 1 of your leagues are complete" in r.text


def test_hiding_completed_is_remembered(client, db_conn):
    _league(db_conn, "All Done", state="complete")

    client.get("/leagues/?completed=hide")
    assert "All Done" not in client.get("/leagues/").text

    client.get("/leagues/?completed=show")
    assert "All Done" in client.get("/leagues/").text
