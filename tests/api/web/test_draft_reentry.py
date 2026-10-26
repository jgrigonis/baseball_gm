# tests/api/web/test_draft_reentry.py
"""
Coming back into a league after its draft has run lands on the draft results,
not the board. The board is only for a draft still to run.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app


@pytest.fixture
def league_gm(db_conn, factory):
    league = factory.league(state="preseason")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    return league, gm, team


@pytest.fixture
def client(db_conn, league_gm):
    _, gm, team = league_gm
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id, "team_id": team.id}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm.id}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("state", ["preseason", "draft"])
def test_reentry_after_draft_goes_to_results(
    client, db_conn, factory, league_gm, state
):
    league, _, _ = league_gm
    db_conn.execute("UPDATE leagues SET state = %s WHERE id = %s", (state, league.id))
    factory.draft(league=league, state="complete")

    r = client.get(f"/leagues/{league.id}/")

    assert r.headers["location"] == f"/leagues/{league.id}/draft/results"


def test_reentry_before_draft_goes_to_board(client, factory, league_gm):
    league, _, _ = league_gm
    factory.draft(league=league, state="pending")

    r = client.get(f"/leagues/{league.id}/")

    assert r.headers["location"] == f"/leagues/{league.id}/draft"


def test_board_redirects_to_results_once_draft_is_done(client, factory, league_gm):
    league, _, _ = league_gm
    factory.draft(league=league, state="complete")

    r = client.get(f"/leagues/{league.id}/draft")

    assert r.status_code == 302
    assert r.headers["location"] == f"/leagues/{league.id}/draft/results"
