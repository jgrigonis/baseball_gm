# tests/api/web/test_lineup_tab.py
"""The Lineup tab saves a lineup for each hand of opposing starter."""

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.team_repo import TeamRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    hitters = [
        factory.rated_player(team, league, status="26man", name=f"H{i}")
        for i in range(9)
    ]
    return league, team, gm, hitters


@pytest.fixture
def client(db_conn, setup):
    _, team, gm, _ = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": team.id,
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


POSITIONS = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]


def body(hitters, vs_hand):
    return {
        "vs_hand": vs_hand,
        "lineup": [
            {"player_id": h.id, "batting_order": i + 1, "position": pos}
            for i, (h, pos) in enumerate(zip(hitters, POSITIONS))
        ],
    }


def test_saves_each_hand_separately(client, db_conn, setup):
    league, _, gm, hitters = setup
    url = f"/leagues/{league.id}/lineup/save"
    assert client.put(url, json=body(hitters, "R")).status_code == 200
    assert client.put(url, json=body(hitters[::-1], "L")).status_code == 200

    saved = LineupPreferenceRepository(db_conn).get_by_gm_id(gm.id)
    assert saved["R"][0]["player_id"] == hitters[0].id
    assert saved["L"][0]["player_id"] == hitters[-1].id


def test_page_shows_the_toggle_and_both_lineups(client, setup):
    league, _, _, hitters = setup
    client.put(f"/leagues/{league.id}/lineup/save", json=body(hitters, "L"))

    r = client.get(f"/leagues/{league.id}/lineup")

    assert r.status_code == 200
    assert "vs LHP" in r.text and "vs RHP" in r.text
    first = f'{{"L": [{{"batting_order": 1, "player_id": "{hitters[0].id}"'
    assert first in r.text
    assert '"R": []' in r.text


def test_bad_hand_is_rejected(client, setup):
    league, _, _, hitters = setup
    r = client.put(f"/leagues/{league.id}/lineup/save", json=body(hitters, "X"))
    assert r.status_code == 422


def test_each_player_has_a_face_image(client, db_conn, setup):
    league, team, _, hitters = setup
    t = TeamRepository(db_conn).get_city_and_mascot(team.id)

    r = client.get(f"/leagues/{league.id}/lineup")

    for h in hitters:
        assert f"/faces/{h.id}.svg?age=" in r.text
    assert urlencode({"team": f"{t['city']}|{t['mascot']}"}) in r.text
