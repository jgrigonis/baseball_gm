# tests/api/web/test_standings_view.py
"""The standings remember Divisions or Overall per league, so the refresh
after each sim day (which reloads the plain tab URL) keeps the choice."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.league import divisions


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    opp = factory.team(city="Chicago", mascot="Wind")
    for team in (mine, opp):
        factory.league_season_team(league, season, team)
    divisions.save(
        db_conn,
        league.id,
        [
            divisions.Conference("East", [divisions.Division("North", [mine.id])]),
            divisions.Conference("West", [divisions.Division("South", [opp.id])]),
        ],
    )
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               home_score, away_score, completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 5, 3, 1)""",
        (str(uuid.uuid4()), season.id, mine.id, opp.id),
    )
    gm = factory.gm(team=mine, league=league, is_ai=False)
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    as_gm = {"id": gm.id, "team_id": mine.id}
    app.dependency_overrides[get_current_gm] = lambda: as_gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: as_gm
    yield league
    app.dependency_overrides.clear()


def _active(html: str) -> str:
    return html.split('class="standings-view on">')[1].split("</a>")[0]


def test_overall_sticks_after_a_refresh(setup):
    client = TestClient(app)
    url = f"/leagues/{setup.id}/standings"
    assert _active(client.get(url).text) == "Divisions"
    assert _active(client.get(url + "?view=overall").text) == "Overall"
    # The live refresh asks for the plain URL
    assert _active(client.get(url, headers={"HX-Request": "true"}).text) == "Overall"
    # Picking Divisions again is remembered too
    assert _active(client.get(url + "?view=divisions").text) == "Divisions"
    assert _active(client.get(url).text) == "Divisions"


def test_each_league_remembers_its_own_view(setup):
    client = TestClient(app)
    client.get(f"/leagues/{setup.id}/standings?view=overall")
    other = f"standings_view_{uuid.uuid4()}"
    assert client.cookies.get(f"standings_view_{setup.id}") == "overall"
    assert client.cookies.get(other) is None


def test_extra_columns_start_hidden_behind_a_toggle(setup):
    """Home, Away, L10, RS and RA render but stay hidden until the toggle
    (kept in the browser) shows them, in both views."""
    client = TestClient(app)
    for view in ("divisions", "overall"):
        html = client.get(f"/leagues/{setup.id}/standings?view={view}").text
        assert 'id="standings-main" class="st-hide-extra"' in html
        assert 'id="standings-extra-btn"' in html
        for col in ("Home", "Away", "L10", "RS", "RA"):
            assert f'st-extra" style="text-align:center;">{col}</th>' in html
