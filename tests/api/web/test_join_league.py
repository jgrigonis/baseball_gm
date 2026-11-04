# tests/api/web/test_join_league.py
"""
Joining by code shows an error on the join page when the code is unknown or
the league has already started, instead of silently re-rendering the form.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import personas


@pytest.fixture
def user(db_conn):
    user_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'Joiner')",
        (user_id, user_id),
    )
    return {"id": user_id, "display_name": "Joiner"}


@pytest.fixture
def client(db_conn, user):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _league(db_conn, factory, state, code):
    league = factory.league(state=state)
    db_conn.execute(
        "UPDATE leagues SET join_code = %s WHERE id = %s", (code, league.id)
    )
    return league


def _join(client, code):
    return client.post("/leagues/join", data={"join_code": code})


def test_league_mid_season_says_wait_for_the_offseason(client, db_conn, factory):
    _league(db_conn, factory, "season", "STRTD1")

    r = _join(client, "strtd1")

    assert r.status_code == 200
    assert "between seasons" in r.text
    assert 'value="STRTD1"' in r.text


def test_league_without_late_joiners_says_so(client, db_conn, factory):
    league = _league(db_conn, factory, "offseason", "STRTD2")
    db_conn.execute("UPDATE leagues SET late_joins = FALSE WHERE id = %s", (league.id,))

    r = _join(client, "STRTD2")

    assert "taking new GMs once it has started" in r.text


def test_unknown_code_says_not_found(client):
    r = _join(client, "NOPE00")

    assert r.status_code == 200
    assert "No league found" in r.text


def test_lobby_league_joins(client, db_conn, factory):
    league = _league(db_conn, factory, "lobby", "LOBBY1")

    r = _join(client, "LOBBY1")

    assert r.status_code == 302
    assert r.headers["location"] == f"/leagues/{league.id}/"


def test_joining_takes_an_ai_gms_place(client, db_conn, factory):
    league = _league(db_conn, factory, "lobby", "LOBBY2")
    db_conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))
    personas.fill_lobby(db_conn, league.id)
    assert len(personas.lobby_ai_gms(db_conn, league.id)) == 4

    _join(client, "LOBBY2")

    assert len(personas.lobby_ai_gms(db_conn, league.id)) == 3


def test_existing_gm_of_started_league_goes_to_it(client, db_conn, factory, user):
    league = _league(db_conn, factory, "season", "MEMBR1")
    db_conn.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, %s, 'Joiner', false)",
        (league.id, user["id"]),
    )

    r = _join(client, "MEMBR1")

    assert r.status_code == 302
    assert r.headers["location"] == f"/leagues/{league.id}/"
