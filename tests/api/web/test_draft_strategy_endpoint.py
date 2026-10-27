# tests/api/web/test_draft_strategy_endpoint.py
"""
PUT /leagues/{id}/draft/strategy saves a GM's need chips, age preference and
pins, replacing any Advanced ranked list, and turns away bad input.
POST /leagues/{id}/draft/preview projects the GM's first picks.
The draft tab opens in Strategy mode unless a ranked list is saved.
"""

from types import SimpleNamespace

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
    gm.team_id = team.id
    draft = factory.draft(league=league)
    prospects = [factory.prospect(league_id=league.id) for _ in range(3)]
    return league, gm, draft, prospects


@pytest.fixture
def client(db_conn, setup):
    _, gm, _, _ = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": gm.team_id,
    }
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


def test_saving_a_strategy_replaces_the_ranked_list(client, db_conn, setup):
    league, gm, draft, prospects = setup
    repo = DraftRepository(db_conn)
    repo.save_preferences(draft.id, gm.id, [p.id for p in prospects])

    _put(client, league, {"chips": {"c": 1}})

    assert repo.get_preferences(draft.id, gm.id) == []


class TestPreview:
    @pytest.fixture
    def two_teams(self, db_conn, factory, setup):
        league, gm, draft, prospects = setup
        factory.draft_order(draft, [SimpleNamespace(id=gm.team_id), factory.team()])
        prospects += [factory.prospect(league_id=league.id) for _ in range(10)]
        return league, prospects

    def _preview(self, client, league, body):
        r = client.post(f"/leagues/{league.id}/draft/preview", json=body)
        assert r.status_code == 200
        return r.json()["picks"]

    def test_first_five_picks_in_snake_slots(self, client, two_teams):
        league, _ = two_teams
        picks = self._preview(client, league, {})
        assert [(p["pick"], p["round"]) for p in picks] == [
            (1, 1),
            (4, 2),
            (5, 3),
            (8, 4),
            (9, 5),
        ]

    def test_unsaved_pins_come_first(self, client, db_conn, setup, two_teams):
        league, prospects = two_teams
        _, gm, draft, _ = setup
        pins = [prospects[-1].id, prospects[-2].id]

        picks = self._preview(client, league, {"pins": pins})

        assert [p["player_id"] for p in picks[:2]] == pins
        assert DraftRepository(db_conn).get_strategy(draft.id, gm.id) is None

    def test_pins_other_teams_take_first_are_flagged(self, client, two_teams):
        league, prospects = two_teams
        # Every prospect rates the same, so the AI takes them in name order
        # and three pins can't all last to our second pick.
        pins = [p.id for p in prospects[:3]]
        r = client.post(f"/leagues/{league.id}/draft/preview", json={"pins": pins})
        gone = r.json()["pins_gone"]
        mine = {p["player_id"] for p in r.json()["picks"]}
        assert gone and all(pid in pins and pid not in mine for pid in gone)

    def test_bad_strategy_is_rejected(self, client, two_teams):
        league, _ = two_teams
        r = client.post(f"/leagues/{league.id}/draft/preview", json={"chips": {"x": 1}})
        assert r.status_code == 422

    def test_no_picks_without_a_draft_slot(self, client, setup):
        league, _, _, _ = setup
        assert self._preview(client, league, {}) == []


class TestDraftTabMode:
    def _page(self, client, league):
        r = client.get(f"/leagues/{league.id}/draft", headers={"HX-Request": "true"})
        assert r.status_code == 200
        return r.text

    def test_opens_in_strategy_mode(self, client, setup):
        league, _, _, _ = setup
        page = self._page(client, league)
        assert 'id="strategy-pane"' in page
        assert '"key": "if"' in page and '"label": "Relief Ace"' in page
        assert "const SAVED_PREFS = [];" in page

    def test_saved_strategy_is_on_the_page(self, client, db_conn, setup):
        league, gm, draft, prospects = setup
        DraftRepository(db_conn).save_strategy(
            draft.id, gm.id, DraftStrategy(chips={"of": 2}, pins=[prospects[1].id])
        )
        page = self._page(client, league)
        assert '"chips": {"of": 2}' in page
        assert prospects[1].id in page
