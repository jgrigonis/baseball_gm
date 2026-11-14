# tests/api/web/test_live_draft_routes.py
"""
The live draft's routes (Long Form): Start Draft in a one-person league, the
draft room's poll and short list, a pick, and Run Draft refused.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.league.offseason.snake_draft import ROUNDS


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="draft", mode="longform")
    season = factory.season()
    factory.league_season(league, season)
    draft = factory.draft(league=league, season=season, fmt="interactive")
    ai, me = factory.team(), factory.team()
    factory.gm(team=ai, league=league, is_ai=True)
    gm = factory.gm(team=me, league=league, is_ai=False)
    uid = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, 'P', %s)",
        (uid, uid, uid),
    )
    db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (uid, gm.id))
    factory.draft_order(draft, [ai, me])
    for i in range(ROUNDS * 2 + 3):
        factory.prospect(league_id=league.id, stamina=30 + i % 40)
    return league, draft, ai, me, gm


@pytest.fixture
def client(db_conn, setup):
    _, _, _, me, gm = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id, "team_id": me.id}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_run_draft_is_refused(client, setup):
    league = setup[0]
    r = client.post(f"/leagues/{league.id}/draft/execute")
    assert r.status_code == 409


def test_start_pick_and_poll(client, setup):
    league, _, ai, me, _ = setup
    base = f"/leagues/{league.id}/draft"
    assert client.post(f"{base}/start").status_code == 200
    assert client.post(f"{base}/start").status_code == 409  # already on

    r = client.get(f"{base}/live")
    state = r.json()
    assert state["on_clock"]["you"] is True
    assert state["pick"] == 2 and state["seconds_left"] is None
    assert [p["team"] for p in state["recent"]] and state["recent"][0]["mine"] is False

    nxt = client.get(f"{base}/live/list").json()["next"]
    assert nxt["pick"] == 2 and nxt["players"][0] == nxt["default"]

    r = client.post(f"{base}/pick", json={"player_id": nxt["players"][1]})
    assert r.status_code == 200, r.text
    state = client.get(f"{base}/live").json()
    assert (
        state["pick"] == 3 and state["on_clock"]["you"] is True
    )  # 2-team snake: back to back
    assert nxt["players"][1] in state["taken"]

    r = client.post(f"{base}/pick", json={"player_id": nxt["players"][1]})
    assert r.status_code == 409


def test_draft_tab_shows_the_live_room(client, setup):
    league = setup[0]
    client.post(f"/leagues/{league.id}/draft/start")
    r = client.get(f"/leagues/{league.id}/draft")
    assert r.status_code == 200
    assert 'id="live-section"' in r.text
    assert "Live draft" in r.text
