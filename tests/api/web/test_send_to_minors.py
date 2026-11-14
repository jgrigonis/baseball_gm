# tests/api/web/test_send_to_minors.py
"""The Lineup tab's red − sends a pitcher off the 40-man to the minors."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    pitchers = [
        factory.rated_player(team, league, pitcher=True, name=f"P{i}")
        for i in range(26)
    ]
    return league, season, team, gm, pitchers


@pytest.fixture
def client(db_conn, setup):
    _, _, team, gm, _ = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": team.id,
    }
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def url(league, pid):
    return f"/leagues/{league.id}/roster/{pid}/minors"


def test_sends_him_down_and_clears_his_role(client, db_conn, setup, factory):
    league, season, team, _, pitchers = setup
    factory.rated_player(team, league, name="Spare")  # room for two to go down
    starter, closer = pitchers[0], pitchers[1]
    TeamRotationsRepository(db_conn, league.id).set_rotation(
        team.id, season.id, [starter.id], "2025-04-01"
    )
    bullpen = BullpenRepository(db_conn)
    bullpen.set_roles(
        team.id, season.id, [{"player_id": closer.id, "role": "Closer"}], "2025-04-01"
    )

    assert client.post(url(league, starter.id)).status_code == 200
    assert client.post(url(league, closer.id)).status_code == 200

    status = PlayerStatusRepository(db_conn)
    assert status.get_status(starter.id) == "minors"
    assert status.get_status(closer.id) == "minors"
    assert starter.id not in bullpen.get_active_rotation_player_ids(team.id, season.id)
    assert closer.id not in bullpen.get_roles_map(team.id, season.id)


def test_keeps_25_on_the_40_man(client, db_conn, setup):
    league, _, _, _, pitchers = setup
    assert client.post(url(league, pitchers[0].id)).status_code == 200
    # 25 left: one more would go below the floor.
    r = client.post(url(league, pitchers[1].id))
    assert r.status_code == 422
    assert "at least 25" in r.json()["detail"]
    assert PlayerStatusRepository(db_conn).get_status(pitchers[1].id) == "40man"


def test_only_your_own_40_man(client, db_conn, setup, factory):
    league, _, _, _, pitchers = setup
    other = factory.rated_player(factory.team(), league, pitcher=True)
    assert client.post(url(league, other.id)).status_code == 422
    assert client.post(url(league, pitchers[0].id)).status_code == 200
    assert client.post(url(league, pitchers[0].id)).status_code == 422


def test_lineup_rows_have_the_button(client, setup):
    league = setup[0]
    html = client.get(f"/leagues/{league.id}/lineup").text
    assert "minors-btn" in html
    assert 'title="${DOWN_TITLE}"' in html
    # Blitz: off the 40-man (Long Form takes him off the active roster).
    assert "const LONG_FORM       = false" in html
    assert "'Send him to the minors'" in html
