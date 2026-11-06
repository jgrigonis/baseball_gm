# tests/api/web/test_roster_faces.py
"""The Roster tab shows each player's face, wearing his team's cap."""

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team(city="Tokyo", mascot="Samurai")
    gm = factory.gm(team=team, league=league, is_ai=False)
    players = [
        factory.rated_player(team, league, status="26man", name="Active"),
        factory.rated_player(team, league, status="40man", name="Reserve"),
        factory.rated_player(team, league, status="minors", name="Farmhand"),
    ]
    return league, team, gm, players


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


def test_every_player_on_both_sides_has_a_face(client, setup):
    league, _, _, players = setup

    r = client.get(f"/leagues/{league.id}/roster")

    assert r.status_code == 200
    for p in players:
        assert f"/faces/{p.id}.svg?age=" in r.text
    assert urlencode({"team": "Tokyo|Samurai"}) in r.text


def test_the_roster_tab_badge_counts_players_who_want_a_trade(
    client, setup, monkeypatch
):
    from src.db.repositories.happiness_repo import HappinessRepository

    league, *_ = setup
    monkeypatch.setattr(HappinessRepository, "team_trade_requests", lambda self, t: 2)
    html = client.get(f"/leagues/{league.id}/roster").text
    assert 'id="roster-badge"' in html
    assert 'title="2 players want a trade"' in html
    assert client.get(f"/leagues/{league.id}/roster/trade-requests").json() == {
        "count": 2
    }
