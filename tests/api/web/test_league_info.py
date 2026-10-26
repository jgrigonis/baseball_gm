# tests/api/web/test_league_info.py
"""
Once a league has started, its settings stay in view: the top bar's season
pill opens them, and the League page lists them with who runs each team.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app


@pytest.fixture
def league(db_conn, factory):
    """A league in season 2 of 10 with one human GM and one AI GM."""
    league = factory.league(state="season")
    db_conn.execute(
        "UPDATE leagues SET num_teams = 2, num_seasons = 10, pace_control = 'timer',"
        " decision_window_sec = 90, sim_period_days = 7 WHERE id = %s",
        (league.id,),
    )
    for year in (2025, 2026):
        factory.league_season(league, factory.season(year=year))
    human = factory.gm(
        team=factory.team(city="Boston", mascot="Beans"), league=league, is_ai=False
    )
    factory.gm(team=factory.team(city="Chicago", mascot="Wind"), league=league)
    return league, human


@pytest.fixture
def client(db_conn, league):
    _, gm = league
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm.id, "team_id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_season_pill_shows_progress_and_opens_settings(client, league):
    lg, _ = league

    html = client.get(f"/leagues/{lg.id}/standings").text

    pill = html.split('id="league-info"')[1].split("</details>")[0]
    assert "season 2/10" in pill
    assert "Decision window" in pill
    assert "90s" in pill
    assert "1 human · 1 AI" in pill
    assert f'href="/leagues/{lg.id}/league"' in pill


def test_league_page_lists_settings_and_gms(client, league):
    lg, _ = league

    r = client.get(f"/leagues/{lg.id}/league")

    assert r.status_code == 200
    assert "Season 2 of 10" in r.text
    assert "Boston Beans" in r.text and "Chicago Wind" in r.text
    assert "Days per sim period" in r.text
    assert "Timer" in r.text


def test_league_page_in_the_lobby_goes_to_the_lobby(client, db_conn, league):
    lg, _ = league
    db_conn.execute("UPDATE leagues SET state = 'lobby' WHERE id = %s", (lg.id,))

    r = client.get(f"/leagues/{lg.id}/league")

    assert r.status_code == 307
    assert r.headers["location"] == f"/leagues/{lg.id}/"


def test_lobby_still_shows_its_settings(client, db_conn, league):
    lg, _ = league
    db_conn.execute("UPDATE leagues SET state = 'lobby' WHERE id = %s", (lg.id,))

    html = client.get(f"/leagues/{lg.id}/").text

    assert "Decision window" in html
    assert 'id="league-info"' not in html
    assert ">10<" in html  # seasons, with no progress before the start
