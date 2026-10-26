# tests/api/web/test_public_league_viewers.py
"""
Anyone signed in can follow a public league once it has started, without
joining: its standings, leaders, team stats, playoffs, draft results and
history. The pages built around one GM's own team stay GM-only, and so does
every action. Private leagues stay GM-only throughout.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app


@pytest.fixture
def user_id(db_conn):
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username, password_hash)"
        " VALUES (%s, %s, 'Viewer', %s, 'x')",
        (uid, uid, uid),
    )
    return uid


@pytest.fixture
def client(db_conn, user_id):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user_id,
        "has_password": True,
        "display_name": "Viewer",
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _league(db, factory, state="season", is_public=True):
    """A league in its 2025 season with two teams, one of them run by a GM
    who isn't the viewer."""
    league = factory.league(state=state)
    db.execute(
        "UPDATE leagues SET is_public = %s WHERE id = %s", (is_public, league.id)
    )
    season = factory.season(year=2025)
    factory.league_season(league, season)
    home = factory.team(city="Boston", mascot="Beans")
    away = factory.team(city="Chicago", mascot="Wind")
    for team in (home, away):
        factory.league_season_team(league, season, team)
    factory.gm(team=home, league=league, is_ai=False)
    factory.gm(team=away, league=league)
    db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               home_score, away_score, winner_id, completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 5, 3, %s, 1)""",
        (str(uuid.uuid4()), season.id, home.id, away.id, home.id),
    )
    return league, home


VIEWABLE = [
    "standings",
    "leaders",
    "stats",
    "playoffs",
    "history",
    "season-summary",
    "retirement",
    "draft/results",
]
GM_ONLY = ["schedule", "roster", "lineup", "strategy", "draft"]


@pytest.mark.parametrize("page", VIEWABLE)
def test_viewer_sees_league_pages(client, db_conn, factory, page):
    league, _ = _league(db_conn, factory)

    r = client.get(f"/leagues/{league.id}/{page}")

    assert r.status_code == 200
    assert "Viewing" in r.text


@pytest.mark.parametrize("page", GM_ONLY)
def test_viewer_cant_open_gm_pages(client, db_conn, factory, page):
    league, _ = _league(db_conn, factory)

    r = client.get(f"/leagues/{league.id}/{page}", headers={"accept": "text/html"})

    assert r.status_code == 303
    assert r.headers["location"] == "/leagues/"


def test_viewer_tabs_leave_out_gm_pages(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    tabs = html.split('id="tab-bar"')[1].split("</nav>")[0]
    for tab in ("standings", "leaders", "stats"):
        assert f'hx-get="/leagues/{league.id}/{tab}"' in tabs
    for tab in GM_ONLY:
        assert f'hx-get="/leagues/{league.id}/{tab}"' not in tabs


def test_viewer_gets_no_sim_controls(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert "Play Day" not in html
    assert "/news`" not in html


def test_standings_link_each_team_to_its_roster(client, db_conn, factory):
    league, home = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/standings").text

    assert f"/leagues/{league.id}/stats?team_id={home.id}" in html


def test_viewer_stats_start_on_a_team(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    html = client.get(f"/leagues/{league.id}/stats").text

    assert "selected" in html.split('id="team-select"')[1].split("</select>")[0]


def test_viewer_cant_sim(client, db_conn, factory):
    league, _ = _league(db_conn, factory)

    r = client.post(f"/leagues/{league.id}/sim", json={"count": 1})

    assert r.status_code == 403


@pytest.mark.parametrize(
    "state, page", [("season", "standings"), ("complete", "history")]
)
def test_league_link_sends_viewer_to_a_viewable_page(
    client, db_conn, factory, state, page
):
    league, _ = _league(db_conn, factory, state=state)

    r = client.get(f"/leagues/{league.id}/")

    assert r.headers["location"] == f"/leagues/{league.id}/{page}"


@pytest.mark.parametrize("state, is_public", [("season", False), ("lobby", True)])
def test_private_and_lobby_leagues_stay_closed(
    client, db_conn, factory, state, is_public
):
    league, _ = _league(db_conn, factory, state=state, is_public=is_public)

    r = client.get(f"/leagues/{league.id}/standings", headers={"accept": "text/html"})

    assert r.headers["location"] == "/leagues/"
