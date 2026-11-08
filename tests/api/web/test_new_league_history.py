# tests/api/web/test_new_league_history.py
"""Years of history (the league's backstory) is picked on the new league
form, under Advanced settings."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.db.repositories.league_repo import LeagueRepository
from src.league.league_constants import DEFAULT_BACKSTORY_YEARS, MAX_BACKSTORY_YEARS


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
        "is_contributor": True,  # real seasons are for paid contributors
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _years(client, db_conn, **form):
    r = client.post("/leagues/new", data={"name": "Fresh League", **form})
    league_id = r.headers["location"].split("/")[2]
    return LeagueRepository(db_conn).get_by_id(league_id)["backstory_years"]


def test_default(client, db_conn):
    assert _years(client, db_conn) == DEFAULT_BACKSTORY_YEARS


@pytest.mark.parametrize("years", [0, 3, MAX_BACKSTORY_YEARS])
def test_picked_on_the_form(client, db_conn, years):
    assert _years(client, db_conn, backstory_years=str(years)) == years


@pytest.mark.parametrize("years", [-1, MAX_BACKSTORY_YEARS + 1])
def test_out_of_range_is_refused(client, db_conn, years):
    r = client.post(
        "/leagues/new", data={"name": "Fresh League", "backstory_years": str(years)}
    )
    assert r.status_code >= 400


def test_the_form_has_it_under_advanced(client):
    html = client.get("/leagues/new").text
    advanced = html[html.index('class="advanced-settings"') :]
    assert 'name="backstory_years"' in advanced
    assert f'value="{DEFAULT_BACKSTORY_YEARS}"' in advanced


# ── Real seasons (src/league/real_seasons/) ──────────────────────────────────


def test_a_real_season_is_30_teams_with_no_history(client, db_conn):
    r = client.post(
        "/leagues/new",
        data={
            "name": "Real",
            "real_season": "2025",
            "num_teams": "20",
            "backstory_years": "5",
        },
    )
    league = LeagueRepository(db_conn).get_by_id(r.headers["location"].split("/")[2])
    assert league["real_season"] == 2025
    assert league["num_teams"] == 30
    assert league["backstory_years"] == 0


def test_a_generated_league_has_no_real_season(client, db_conn):
    r = client.post("/leagues/new", data={"name": "Made up"})
    league = LeagueRepository(db_conn).get_by_id(r.headers["location"].split("/")[2])
    assert league["real_season"] is None


def test_a_season_without_data_is_refused(client):
    r = client.post("/leagues/new", data={"name": "Real", "real_season": "1888"})
    assert r.status_code >= 400


def test_the_form_offers_the_real_seasons(client):
    html = client.get("/leagues/new").text
    assert 'name="real_season"' in html
    assert '<option value="2025">' in html


def test_real_seasons_are_for_paid_contributors(client, db_conn):
    unpaid = dict(app.dependency_overrides[get_current_user](), is_contributor=False)
    app.dependency_overrides[get_current_user] = lambda: unpaid
    html = client.get("/leagues/new").text
    assert '<option value="2025" disabled>' in html
    assert "(paid contributors)" in html
    r = client.post("/leagues/new", data={"name": "Real", "real_season": "2025"})
    assert r.status_code == 403
    # Generated leagues are open to everyone.
    r = client.post("/leagues/new", data={"name": "Made up"})
    assert r.status_code in (302, 303)
