# tests/api/web/test_new_long_form_league.py
"""
Long Form on the New League form (Josh, 2026-11-14): Confirmed pace only,
trades on, and its own draft pick timer. The admin can't move a Long Form
league to Timer pace either.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import admin
from src.db.repositories.league_repo import LeagueRepository


@pytest.fixture
def client(db_conn):
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username, password_hash)"
        " VALUES (%s, %s, 'Alice', %s, 'x')",
        (uid, uid, uid),
    )
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {
        "id": uid,
        "has_password": True,
        "display_name": "Alice",
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _create(client, db_conn, **form):
    r = client.post("/leagues/new", data={"name": "Long League", **form})
    assert r.status_code in (302, 303), r.text
    return LeagueRepository(db_conn).get_by_id(r.headers["location"].split("/")[2])


def test_the_form_offers_long_form(client):
    r = client.get("/leagues/new")
    assert '<option value="longform"' in r.text
    assert "Coming Soon</option>" not in r.text.split("pace-control")[0]
    assert 'name="pick_timer_sec"' in r.text


def test_long_form_is_confirmed_pace_with_trades(client, db_conn):
    league = _create(
        client,
        db_conn,
        mode="longform",
        pace_control="timer",
        num_seasons="25",
        pick_timer_sec="60",
        trades_enabled=["false", "true"],
    )
    assert league["mode"] == "longform"
    assert league["pace_control"] == "confirmed"
    assert league["num_seasons"] == 25
    assert league["pick_timer_sec"] == 60
    assert league["trades_enabled"]


def test_pick_timer_out_of_range_is_refused(client):
    r = client.post(
        "/leagues/new",
        data={"name": "L", "mode": "longform", "pick_timer_sec": "5"},
    )
    assert r.status_code >= 400


def test_admin_cant_set_long_form_to_timer_pace():
    league = {"mode": "longform", "state": "lobby", "backstory_years": 0}
    settings = {
        "name": "L",
        "mode": "longform",
        "pace_control": "timer",
        "backstory_years": 0,
        **{k: 0 for k in admin.NUMBER_RANGES},
    }
    league.update({k: 0 for k in admin.NUMBER_RANGES})
    assert "Confirmed" in admin.settings_error(league, settings, 0)
