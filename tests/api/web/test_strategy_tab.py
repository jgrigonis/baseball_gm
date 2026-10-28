# tests/api/web/test_strategy_tab.py
"""The Strategy tab shows each setting's saved value and saves the sliders."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.api.routers.strategy import SETTINGS
from src.db.repositories.gm_repo import GMRepository


@pytest.fixture
def gm(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    gm.league_id, gm.team_id = league.id, team.id
    return gm


@pytest.fixture
def client(db_conn, gm):
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": gm.team_id,
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_saves_every_setting(client, db_conn, gm):
    form = {
        "lineup_style": 3,
        "baserunning": 4,
        "sac_bunt": 0,
        "rest_days": 2,
        "starter_usage": 2,
        "closer_usage": 1,
        "bullpen_pref": 1,
        "rotation_size": 0,
        "skip_fifth_starter": 1,
        "playoff_rotation": 0,
        "tired_starters": 2,
    }
    r = client.post(f"/leagues/{gm.league_id}/strategy", data=form)
    assert r.status_code == 200

    row = GMRepository(db_conn).get_profile(gm.id)
    assert row["lineup_style"] == "power-first"
    assert row["baserunning"] == "very-aggressive"
    assert row["sac_bunt"] == "never"
    assert row["rest_days"] == "rest-often"
    assert row["closer_usage"] == "high-leverage"
    assert row["rotation_size"] == 4
    assert row["skip_fifth_starter"] is True
    assert row["playoff_rotation"] == "3"
    assert row["tired_starters"] == "protect"


def test_out_of_range_is_clamped_and_junk_ignored(client, db_conn, gm):
    client.post(
        f"/leagues/{gm.league_id}/strategy",
        data={"baserunning": 99, "sac_bunt": "lots"},
    )
    row = GMRepository(db_conn).get_profile(gm.id)
    assert row["baserunning"] == "very-aggressive"
    assert row["sac_bunt"] == "situational"


def test_page_shows_saved_values(client, db_conn, gm):
    GMRepository(db_conn).save_profile(
        gm.id, {"baserunning": "conservative", "rotation_size": 6}
    )
    r = client.get(f"/leagues/{gm.league_id}/strategy", headers={"HX-Request": "true"})
    assert r.status_code == 200
    html = r.text
    assert 'name="baserunning" min="0" max="4" step="1"\n         value="1"' in html
    assert 'name="rotation_size" min="0" max="2" step="1"\n         value="2"' in html
    assert 'hx-post="/leagues/' in html  # the form posts, matching the route


def test_every_setting_is_a_profile_column(db_conn, gm):
    row = GMRepository(db_conn).get_profile(gm.id)
    for _, settings in SETTINGS:
        for s in settings:
            assert s.name in row
            assert row[s.name] in s.values
            assert len(s.labels) == len(s.values)
