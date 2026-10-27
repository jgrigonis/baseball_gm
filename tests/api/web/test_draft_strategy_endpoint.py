# tests/api/web/test_draft_strategy_endpoint.py
"""
PUT /leagues/{id}/draft/strategy saves a GM's need chips, age preference and
pins, and turns away bad input.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.db.repositories.draft_repo import DraftRepository
from src.league.offseason.draft_strategy import DraftStrategy


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="draft")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    draft = factory.draft(league=league)
    prospects = [factory.prospect(league_id=league.id) for _ in range(3)]
    return league, gm, draft, prospects


@pytest.fixture
def client(db_conn, setup):
    _, gm, _, _ = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id, "team_id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _put(client, league, body):
    return client.put(f"/leagues/{league.id}/draft/strategy", json=body)


def test_saves_strategy(client, db_conn, setup):
    league, gm, draft, prospects = setup
    pins = [prospects[2].id, prospects[0].id]

    r = _put(
        client, league, {"chips": {"if": 3, "power": 1}, "age_pref": 0.5, "pins": pins}
    )

    assert r.status_code == 200
    assert DraftRepository(db_conn).get_strategy(draft.id, gm.id) == DraftStrategy(
        chips={"if": 3, "power": 1}, age_pref=0.5, pins=pins
    )


def test_duplicate_pins_are_dropped(client, db_conn, setup):
    league, gm, draft, prospects = setup
    pid = prospects[0].id

    _put(client, league, {"pins": [pid, pid]})

    assert DraftRepository(db_conn).get_strategy(draft.id, gm.id).pins == [pid]


@pytest.mark.parametrize(
    "body",
    [
        {"chips": {"2b": 2}},
        {"chips": {"if": 5}},
        {"age_pref": -3},
        {"pins": ["not-a-prospect"]},
    ],
)
def test_bad_input_is_rejected(client, db_conn, setup, body):
    league, gm, draft, _ = setup

    r = _put(client, league, body)

    assert r.status_code == 422
    assert DraftRepository(db_conn).get_strategy(draft.id, gm.id) is None


def test_completed_draft_is_rejected(client, db_conn, setup):
    league, _, draft, _ = setup
    db_conn.execute("UPDATE drafts SET state = 'complete' WHERE id = %s", (draft.id,))

    assert _put(client, league, {}).status_code == 409
