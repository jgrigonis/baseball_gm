# tests/api/web/test_request_bodies.py
"""
Handlers that do blocking work are plain ``def`` so FastAPI runs them in its
thread pool, and they read their JSON through pydantic models. The models
must keep accepting every payload the dashboard JS sends.
"""

import inspect

import pytest
from pydantic import ValidationError

from src.api import dependencies
from src.api.routers import draft, lineup, roster, sim
from src.api.schemas import (
    DraftPreferencesRequest,
    LineupSaveRequest,
    RosterSaveRequest,
    RotationSaveRequest,
    SimRequest,
)


@pytest.mark.parametrize(
    "fn",
    [
        sim.sim_games,
        lineup.save_lineup_prefs,
        lineup.save_rotation,
        lineup.save_bullpen,
        roster.save_roster_put,
        draft.save_draft_preferences,
        dependencies.get_current_user,
        dependencies.get_optional_user,
        dependencies.get_current_gm,
        dependencies.get_commissioner,
    ],
)
def test_blocking_handlers_are_not_async(fn):
    assert not inspect.iscoroutinefunction(fn)


class TestSimRequest:
    def test_defaults_to_one_day(self):
        assert SimRequest().count == 1

    def test_season(self):
        assert SimRequest(count="season").count == "season"

    def test_numeric_string_is_a_number(self):
        assert SimRequest(count="3").count == 3

    def test_other_strings_are_rejected(self):
        with pytest.raises(ValidationError):
            SimRequest(count="injury")


class TestLineupSaveRequest:
    def test_dashboard_payload(self):
        body = LineupSaveRequest(
            lineup=[{"player_id": "p1", "batting_order": 1, "position": "ss"}]
        )
        assert [s.model_dump() for s in body.lineup] == [
            {"player_id": "p1", "batting_order": 1, "position": "ss"}
        ]

    def test_position_is_optional(self):
        body = LineupSaveRequest(lineup=[{"player_id": "p1", "batting_order": 1}])
        assert body.lineup[0].position is None

    def test_missing_lineup_is_empty(self):
        assert LineupSaveRequest().lineup == []


class TestRotationSaveRequest:
    def test_null_pointer(self):
        body = RotationSaveRequest(rotation=["a", "b"], pointer_pid=None)
        assert body.pointer_pid is None

    def test_missing_fields(self):
        body = RotationSaveRequest()
        assert body.rotation == [] and body.pointer_pid is None


def test_extra_fields_are_ignored():
    assert RosterSaveRequest(forty_man=["a"], junk=1).forty_man == ["a"]
    assert DraftPreferencesRequest(player_ids=["a"], junk=1).player_ids == ["a"]


def test_playoff_sim_returns_its_result():
    """The playoffs page reads games_played etc. from this response; the
    router split had dropped the return, so it answered null."""
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_gm
    from src.api.main import app

    app.dependency_overrides[get_current_gm] = lambda: {"id": "gm", "team_id": "t"}
    try:
        with (
            patch("src.api.database.get_connection", return_value=MagicMock()),
            patch.object(sim, "sim_playoff", return_value={"games_played": 2}),
            patch.object(sim, "LeagueRepository") as repo,
        ):
            repo.return_value.get_state.return_value = "playoffs"
            r = TestClient(app).post("/leagues/L/playoffs/sim?mode=game")
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert r.json() == {"games_played": 2, "league_state": "playoffs"}
