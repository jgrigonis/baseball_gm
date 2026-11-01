# tests/api/web/test_leagues_index.py
"""
The leagues page shows each league's phase and season ("Playoffs 3"), how
many human GMs it has, and when it was last played.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.routers.leagues import state_label
from src.db.repositories.league_repo import LeagueRepository


def _human(db, factory, league, name):
    gm = factory.gm(league=league, is_ai=False)
    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username, password_hash)"
        " VALUES (%s, %s, %s, %s, 'x')",
        (user_id, user_id, name, user_id),
    )
    db.execute("UPDATE gms SET user_id = %s WHERE id = %s", (user_id, gm.id))
    return user_id


@pytest.fixture
def league(db_conn, factory):
    league = factory.league(state="playoffs")
    for year in (2025, 2026, 2027):
        factory.league_season(league, factory.season(year=year))
    return league


@pytest.fixture
def user_id(db_conn, factory, league):
    uid = _human(db_conn, factory, league, "Alice")
    _human(db_conn, factory, league, "Bob")
    factory.gm(league=league, is_ai=True)
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


@pytest.mark.parametrize(
    "state, season, label",
    [
        ("lobby", 0, "Lobby"),
        ("draft", 1, "Draft 1"),
        ("season", 2, "Season 2"),
        ("playoffs", 3, "Playoffs 3"),
        ("offseason", 3, "Offseason 3"),
        ("complete", 10, "Complete"),
    ],
)
def test_state_label(state, season, label):
    assert state_label(state, season) == label


def test_shows_phase_and_season_number(client, league):
    r = client.get("/leagues/")

    assert r.status_code == 200
    assert "Playoffs 3" in r.text


def test_counts_only_human_gms(client, league):
    r = client.get("/leagues/")

    assert 'title="Human GMs">2</td>' in r.text


def test_never_played_shows_a_dash(client, db_conn, league):
    db_conn.execute(
        "UPDATE leagues SET last_played_at = NULL WHERE id = %s", (league.id,)
    )

    r = client.get("/leagues/")

    assert "local-time" not in r.text.split("<script>")[0]


def test_shows_last_played_date(client, db_conn, league):
    db_conn.execute(
        "UPDATE leagues SET last_played_at = '2026-10-25 12:00+00' WHERE id = %s",
        (league.id,),
    )

    r = client.get("/leagues/")

    assert "Oct 25, 2026" in r.text


def test_changing_state_marks_the_league_played(db_conn, league):
    LeagueRepository(db_conn).set_state(league.id, "offseason")

    row = db_conn.execute(
        "SELECT last_played_at FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()
    assert row["last_played_at"] is not None


def _give_team(db, user_id, team):
    db.execute("UPDATE gms SET team_id = %s WHERE user_id = %s", (team.id, user_id))


def test_shows_the_badge_of_the_team_the_gm_runs(client, db_conn, factory, user_id):
    _give_team(db_conn, user_id, factory.team(city="Portland", mascot="Pines"))

    r = client.get("/leagues/")

    assert 'class="league-team" title="Portland Pines"' in r.text


def test_no_badge_while_still_in_the_lobby(client, db_conn, factory, league, user_id):
    _give_team(db_conn, user_id, factory.team(city="Portland", mascot="Pines"))
    db_conn.execute("UPDATE leagues SET state = 'lobby' WHERE id = %s", (league.id,))

    r = client.get("/leagues/")

    assert "league-team" not in r.text.split("<style>")[0]


def test_no_badge_without_a_team(client, db_conn, user_id):
    db_conn.execute("UPDATE gms SET team_id = NULL WHERE user_id = %s", (user_id,))

    r = client.get("/leagues/")

    assert "league-team" not in r.text.split("<style>")[0]
