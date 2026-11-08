# tests/api/test_custom_teams.py
"""My Teams: custom teams of real player-seasons, shared by code
(routers/custom_teams.py, services/custom_teams.py)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import custom_teams as ct
from src.db.repositories.custom_team_repo import CustomTeamRepository


def _user(db, contributor=False):
    uid = str(uuid.uuid4())
    name = f"gm-{uid[:8]}"
    db.execute(
        """INSERT INTO users (id, session_token, display_name, username, is_contributor)
           VALUES (%s, %s, %s, %s, %s)""",
        (uid, uid, name, name, contributor),
    )
    return {
        "id": uid,
        "username": name,
        "has_password": False,
        "is_admin": False,
        "is_contributor": contributor,
    }


@pytest.fixture
def josh(db_conn):
    return _user(db_conn, contributor=True)


@pytest.fixture
def pat(db_conn):
    return _user(db_conn)


@pytest.fixture
def as_user(db_conn):
    who = {}
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: who["user"]

    def switch(user):
        who["user"] = user
        return TestClient(app)

    yield switch
    app.dependency_overrides.clear()


def _new_team(client, name="Murderers' Row"):
    r = client.post("/teams/", data={"name": name}, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"].rsplit("/", 1)[1]


def _team(db, team_id):
    return CustomTeamRepository(db).get(team_id)


def test_contributor_builds_a_team(as_user, db_conn, josh):
    client = as_user(josh)
    team_id = _new_team(client)
    html = client.get(f"/teams/{team_id}?q=ruth 1927").text
    assert "Murderers&#39; Row" in html
    assert "Babe Ruth" in html and 'value="ruthba01-1927"' in html

    r = client.post(
        f"/teams/{team_id}/add",
        data={"key": "ruthba01-1927", "q": "ruth 1927"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/teams/{team_id}?q=ruth%201927#search"
    assert _team(db_conn, team_id)["players"] == [
        {"key": "ruthba01-1927", "skills": None}
    ]
    html = client.get(f"/teams/{team_id}").text
    assert 'id="slot-0"' in html and "Needs at least 10 pitchers" in html


def test_my_teams_lists_them(as_user, josh):
    client = as_user(josh)
    _new_team(client, "Old Timers")
    html = client.get("/teams/").text
    assert "Old Timers" in html and "0/26" in html
    assert 'href="/teams/"' in html  # menu link for contributors


def test_no_duplicates_and_a_full_roster(as_user, db_conn, josh):
    client = as_user(josh)
    team_id = _new_team(client)
    client.post(f"/teams/{team_id}/add", data={"key": "ruthba01-1927"})
    r = client.post(f"/teams/{team_id}/add", data={"key": "ruthba01-1927"})
    assert r.status_code == 400 and "already on the team" in r.text
    keys = [f"x-{i}" for i in range(ct.ROSTER_MAX)]
    CustomTeamRepository(db_conn).save_players(
        team_id, [{"key": k, "skills": None} for k in keys]
    )
    r = client.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    assert r.status_code == 400 and "holds 26 players" in r.text


def test_edit_and_reset_skills(as_user, db_conn, josh):
    client = as_user(josh)
    team_id = _new_team(client)
    client.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    html = client.get(f"/teams/{team_id}/players/0").text
    assert 'name="power"' in html and "Real 98" in html

    form = {"power": "100", "speed": "", "contact": "70"}
    r = client.post(f"/teams/{team_id}/players/0", data=form, follow_redirects=False)
    assert r.status_code == 303
    skills = _team(db_conn, team_id)["players"][0]["skills"]
    assert skills["power"] == 100 and skills["contact"] == 70
    assert skills["speed"] == 55  # blank keeps the real value
    assert "ct-edited" in client.get(f"/teams/{team_id}").text

    r = client.post(f"/teams/{team_id}/players/0", data={"power": "101"})
    assert r.status_code == 400 and "from 1 to 100" in r.text

    client.post(f"/teams/{team_id}/players/0/reset")
    assert _team(db_conn, team_id)["players"][0]["skills"] is None


def test_matching_the_real_ratings_is_no_edit(as_user, db_conn, josh):
    client = as_user(josh)
    team_id = _new_team(client)
    client.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    client.post(f"/teams/{team_id}/players/0", data={"power": "98"})
    assert _team(db_conn, team_id)["players"][0]["skills"] is None


def test_remove_rename_delete(as_user, db_conn, josh):
    client = as_user(josh)
    team_id = _new_team(client)
    client.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    client.post(f"/teams/{team_id}/remove", data={"slot": "0"})
    assert _team(db_conn, team_id)["players"] == []
    client.post(f"/teams/{team_id}/rename", data={"name": "  The   Kids "})
    assert _team(db_conn, team_id)["name"] == "The Kids"
    client.post(f"/teams/{team_id}/delete")
    assert _team(db_conn, team_id) is None


def test_someone_else_cannot_open_or_change_your_team(as_user, db_conn, josh, pat):
    team_id = _new_team(as_user(josh))
    other = as_user(pat)
    assert other.get(f"/teams/{team_id}").status_code == 404
    r = other.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    assert r.status_code == 404
    assert other.post(f"/teams/{team_id}/delete").status_code == 404
    assert _team(db_conn, team_id) is not None


def test_non_contributors_cannot_build(as_user, db_conn, pat):
    client = as_user(pat)
    html = client.get("/teams/").text
    assert "for paid contributors" in html
    assert 'action="/teams/" ' not in html and "New team" not in html
    r = client.post("/teams/", data={"name": "Mine"}, follow_redirects=False)
    assert "paid%20contributors" in r.headers["location"]
    assert CustomTeamRepository(db_conn).list_for(pat["id"]) == []


def test_share_code_view_and_copy(as_user, db_conn, josh, pat):
    team_id = _new_team(as_user(josh))
    client = as_user(josh)
    client.post(f"/teams/{team_id}/add", data={"key": "griffke02-1997"})
    client.post(f"/teams/{team_id}/players/0", data={"power": "100"})
    code = _team(db_conn, team_id)["share_code"]

    # Anyone signed in can look; only contributors can save a copy.
    viewer = as_user(pat)
    html = viewer.get(f"/teams/shared/{code.lower()}").text
    assert "Ken Griffey" in html and "Save a copy" not in html
    r = viewer.post(f"/teams/shared/{code}/copy", follow_redirects=False)
    assert "paid%20contributors" in r.headers["location"]

    fan = _user(db_conn, contributor=True)
    client = as_user(fan)
    r = client.post(
        "/teams/open", data={"code": f" {code[:4]}-{code[4:]} "}, follow_redirects=False
    )
    assert r.headers["location"] == f"/teams/shared/{code}"
    assert "Save a copy" in client.get(f"/teams/shared/{code}").text
    r = client.post(f"/teams/shared/{code}/copy", follow_redirects=False)
    copy_id = r.headers["location"].rsplit("/", 1)[1]
    copy = _team(db_conn, copy_id)
    assert copy["owner_id"] == fan["id"] and copy["copied_from"] == team_id
    assert copy["share_code"] != code
    assert copy["players"][0]["skills"]["power"] == 100

    # The copy is its own team.
    client.post(f"/teams/{copy_id}/remove", data={"slot": "0"})
    assert len(_team(db_conn, team_id)["players"]) == 1


def test_unknown_share_code(as_user, josh):
    r = as_user(josh).get("/teams/shared/NOPE1234")
    assert r.status_code == 404 and "share code" in r.text


def test_summary_counts_what_the_team_needs():
    rows = [{"is_pitcher": True, "pos": "sp"}] * 5 + [
        {"is_pitcher": True, "pos": "rp"}
    ] * 5
    rows += [{"is_pitcher": False, "pos": "c"}] + [
        {"is_pitcher": False, "pos": "ss"}
    ] * 3
    s = ct.summary(rows)
    assert s["ready"] and s["pitchers"] == 10 and s["hitters"] == 4
    s = ct.summary(rows[1:-4])
    assert s["needs"] == [
        "at least 10 pitchers",
        "at least 5 starting pitchers",
        "a catcher",
    ]
