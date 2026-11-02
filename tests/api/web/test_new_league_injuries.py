# tests/api/web/test_new_league_injuries.py
"""
Injuries are a setting picked when a league is created. Speed Blitz starts
with them off and Blitz with them on, and the GM can flip either. The sim and
the Until Injury button follow the league's setting, not its mode.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.db.repositories.league_repo import LeagueRepository


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


def _create(client, db_conn, **form):
    r = client.post("/leagues/new", data={"name": "Fresh League", **form})
    league_id = r.headers["location"].split("/")[2]
    return LeagueRepository(db_conn).get_by_id(league_id)["injuries_enabled"]


# The form always sends "false" from a hidden input, then "true" from the
# checkbox when it's ticked.
@pytest.mark.parametrize(
    "form, expected",
    [
        ({"mode": "blitz"}, True),
        ({"mode": "speed_blitz"}, False),
        ({"mode": "blitz", "injuries_enabled": ["false", "true"]}, True),
        ({"mode": "blitz", "injuries_enabled": "false"}, False),
        ({"mode": "speed_blitz", "injuries_enabled": ["false", "true"]}, True),
        ({"mode": "speed_blitz", "injuries_enabled": "false"}, False),
    ],
)
def test_new_league_injuries(client, db_conn, form, expected):
    assert _create(client, db_conn, **form) is expected


def test_tutorial_league_has_no_injuries(client, db_conn):
    r = client.post("/leagues/tutorial")
    league_id = r.headers["location"].split("/")[2]
    assert LeagueRepository(db_conn).get_by_id(league_id)["injuries_enabled"] is False


def test_sim_follows_the_leagues_setting(db_conn, factory):
    repo = LeagueRepository(db_conn)
    assert repo.injuries_enabled(
        factory.league(mode="speed_blitz", injuries_enabled=True).id
    )
    assert not repo.injuries_enabled(
        factory.league(mode="blitz", injuries_enabled=False).id
    )
    assert repo.injuries_enabled(factory.league(mode="blitz").id)
    assert not repo.injuries_enabled(factory.league(mode="speed_blitz").id)


# Weighted is the default schedule: the box starts ticked, and a form that
# leaves the field out (an old form or a script) gets it too.
@pytest.mark.parametrize(
    "form, expected",
    [
        ({}, True),
        ({"weighted_schedule": ["false", "true"]}, True),
        ({"weighted_schedule": "false"}, False),
    ],
)
def test_new_league_weighted_schedule(client, db_conn, form, expected):
    r = client.post("/leagues/new", data={"name": "Fresh League", **form})
    league_id = r.headers["location"].split("/")[2]
    assert (
        LeagueRepository(db_conn).get_by_id(league_id)["weighted_schedule"] is expected
    )


def test_new_league_form_ticks_weighted_schedule(client):
    html = client.get("/leagues/new").text
    assert 'id="weighted-schedule" value="true" checked' in html
