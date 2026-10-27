# tests/api/web/test_practice_league.py
"""
The new-user tutorial: practice leagues, the five tabs on the leagues page,
the coach panel's steps, and the first-visit tab tips.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import coach
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


def _league(db, name, state="lobby", is_public=False, is_practice=False):
    league_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO leagues (id, name, state, is_public, is_practice)"
        " VALUES (%s, %s, %s, %s, %s)",
        (league_id, name, state, is_public, is_practice),
    )
    return league_id


def _join(db, league_id, user_id):
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai)"
        " VALUES (%s, %s, %s, 'GM', false)",
        (str(uuid.uuid4()), league_id, user_id),
    )


def _tab(client, tab):
    return client.get(f"/leagues/?tab={tab}").text.split('id="leagues-tabs"')[1]


def _practice(client):
    r = client.post("/leagues/practice")
    return r.headers["location"].split("/")[2]


# ── Starting a practice league ────────────────────────────────────────────────


def test_practice_league_is_a_solo_speed_blitz(client, db_conn, user_id):
    league_id = _practice(client)

    league = LeagueRepository(db_conn).get_by_id(league_id)
    assert league["is_practice"]
    assert league["mode"] == "speed_blitz"
    assert league["state"] == "lobby"
    assert league["join_code"] is None
    assert not league["is_public"]
    assert league["num_seasons"] == 5
    assert league["sim_period_days"] == 30
    gm = db_conn.execute(
        "SELECT id FROM gms WHERE league_id = %s AND user_id = %s", (league_id, user_id)
    ).fetchone()
    assert league["commissioner_gm_id"] == gm["id"]


def test_practice_leagues_have_no_limit(client, db_conn):
    first = _practice(client)
    second = _practice(client)

    repo = LeagueRepository(db_conn)
    assert repo.get_by_id(first)["name"] == "Practice League 1"
    assert repo.get_by_id(second)["name"] == "Practice League 2"


def test_practice_league_opens_in_the_lobby_with_the_coach(client, db_conn, user_id):
    league_id = _practice(client)
    gm = db_conn.execute(
        "SELECT id FROM gms WHERE league_id = %s", (league_id,)
    ).fetchone()
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm["id"]}

    r = client.get(f"/leagues/{league_id}/")

    assert 'id="coach-panel"' in r.text
    assert "Start the league" in r.text
    assert "Practice league" in r.text


def test_other_leagues_have_no_coach(client, db_conn, user_id):
    league_id = _league(db_conn, "Real One")
    _join(db_conn, league_id, user_id)
    gm = db_conn.execute(
        "SELECT id FROM gms WHERE league_id = %s", (league_id,)
    ).fetchone()
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm["id"]}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm["id"]}

    assert 'id="coach-panel"' not in client.get(f"/leagues/{league_id}/").text
    assert client.get(f"/leagues/{league_id}/coach").text == ""


# ── The leagues page's tabs ───────────────────────────────────────────────────


def test_each_league_lands_in_its_tab(client, db_conn, user_id):
    for name, state, practice in [
        ("Learning", "season", True),
        ("Going Now", "season", False),
        ("Long Over", "complete", False),
    ]:
        _join(db_conn, _league(db_conn, name, state, is_practice=practice), user_id)
    _league(db_conn, "Open Lobby", is_public=True)
    _league(db_conn, "On TV", "season", is_public=True)

    tabs = {
        t: _tab(client, t)
        for t in ("practice", "running", "join", "watch", "completed")
    }

    assert "Learning" in tabs["practice"]
    assert "Going Now" in tabs["running"]
    assert "Long Over" in tabs["completed"]
    assert "Open Lobby" in tabs["join"]
    assert "On TV" in tabs["watch"]
    assert "Learning" not in tabs["running"] + tabs["completed"]
    assert "Long Over" not in tabs["running"]


def test_tabs_show_counts(client, db_conn, user_id):
    _join(db_conn, _league(db_conn, "A", "season"), user_id)
    _join(db_conn, _league(db_conn, "B", "draft"), user_id)

    html = client.get("/leagues/").text

    assert 'Running <span class="tab-count">2</span>' in html


def test_someone_new_starts_on_practice(client):
    html = client.get("/leagues/").text

    assert "Welcome to GM Sim." in html
    assert 'action="/leagues/practice"' in html


def test_someone_with_a_league_starts_on_running(client, db_conn, user_id):
    _join(db_conn, _league(db_conn, "Going Now", "season"), user_id)

    html = client.get("/leagues/").text

    assert 'href="/leagues/?tab=running" class="tab-link active"' in html


def test_the_tab_is_remembered(client, db_conn, user_id):
    _join(db_conn, _league(db_conn, "Going Now", "season"), user_id)

    client.get("/leagues/?tab=completed")
    html = client.get("/leagues/").text

    assert 'href="/leagues/?tab=completed" class="tab-link active"' in html


def test_join_tab_takes_a_code(client):
    assert 'action="/leagues/join"' in _tab(client, "join")


def test_practice_leagues_never_show_in_public_lists(client, db_conn):
    _league(db_conn, "Someone's Practice", "season", is_public=True, is_practice=True)

    assert "Someone's Practice" not in _tab(client, "watch")


# ── The coach's steps ─────────────────────────────────────────────────────────


def _steps(db, league_id):
    league = LeagueRepository(db).get_by_id(league_id)
    return {s["key"]: s["done"] for s in coach.coach_steps(db, league)}


def test_marking_a_step_only_counts_in_practice_leagues(db_conn):
    practice = _league(db_conn, "P", "season", is_practice=True)
    real = _league(db_conn, "R", "season")

    coach.mark(db_conn, practice, "roster")
    coach.mark(db_conn, practice, "roster")
    coach.mark(db_conn, real, "roster")

    repo = LeagueRepository(db_conn)
    assert repo.get_by_id(practice)["coach_done"] == ["roster"]
    assert repo.get_by_id(real)["coach_done"] == []


def test_a_new_practice_league_starts_at_the_lobby(db_conn):
    league_id = _league(db_conn, "P", is_practice=True)

    ctx = coach.coach_ctx(db_conn, LeagueRepository(db_conn).get_by_id(league_id))

    assert ctx["current"]["key"] == "start"
    assert ctx["done_count"] == 0


def test_exploring_needs_all_four_tabs(db_conn):
    league_id = _league(db_conn, "P", "season", is_practice=True)
    league = LeagueRepository(db_conn).get_by_id(league_id)

    for tab in ("schedule", "standings", "stats"):
        coach.mark_visit(db_conn, league, tab)
    assert not _steps(db_conn, league_id)["explore"]

    coach.mark_visit(db_conn, league, "leaders")
    assert _steps(db_conn, league_id)["explore"]


def test_the_playoffs_mean_the_season_and_its_games_are_done(db_conn, factory):
    league_id = _league(db_conn, "P", "playoffs", is_practice=True)
    factory.league_season(SimpleNamespace(id=league_id), factory.season(year=2025))

    steps = _steps(db_conn, league_id)

    assert steps["start"] and steps["play"] and steps["season"]
    assert not steps["playoffs"]


def test_a_second_season_finishes_the_tour(db_conn, factory):
    league_id = _league(db_conn, "P", "draft", is_practice=True)
    for year in (2025, 2026):
        factory.league_season(SimpleNamespace(id=league_id), factory.season(year=year))
    for tab in coach.VISIT_STEPS:
        coach.mark(db_conn, league_id, tab)
    for step in ("roster", "lineup"):
        coach.mark(db_conn, league_id, step)

    ctx = coach.coach_ctx(db_conn, LeagueRepository(db_conn).get_by_id(league_id))

    assert ctx["current"] is None
    assert ctx["done_count"] == len(coach.STEPS)


# ── Tab tips ──────────────────────────────────────────────────────────────────


def test_dismissing_and_resetting_tips(client, db_conn, user_id):
    client.post("/tips/dismiss", json={"tip": "roster"})
    client.post("/tips/dismiss", json={"tip": "roster"})
    client.post("/tips/dismiss", json={"tip": "lineup"})

    assert _tips(db_conn, user_id) == ["roster", "lineup"]

    client.post("/tips/reset")

    assert _tips(db_conn, user_id) == []


def _tips(db, user_id):
    return db.execute(
        "SELECT dismissed_tips FROM users WHERE id = %s", (user_id,)
    ).fetchone()["dismissed_tips"]
