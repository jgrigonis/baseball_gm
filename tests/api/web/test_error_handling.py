# tests/api/web/test_error_handling.py
"""
Errors raised inside routes reach the app-level handlers in src/api/main.py:
users get a short message (never a traceback) and get_db rolls back.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.dependencies import (
    NotLeagueGM,
    get_commissioner,
    get_current_gm,
    get_current_user,
    require_active_league,
    require_single_player,
)
from src.api.main import app

LEAGUE = "league-1"
SECRET = "/home/someone/src/secret_module.py"


@pytest.fixture
def conn():
    """The connection get_db hands to the route."""
    conn = MagicMock()
    with patch("src.api.database.get_connection", return_value=conn):
        yield conn


@pytest.fixture
def client(conn):
    gm = {"id": "gm-1", "team_id": "team-1"}
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_commissioner] = lambda: gm
    app.dependency_overrides[require_single_player] = lambda: None
    app.dependency_overrides[require_active_league] = lambda: None
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestUnexpectedErrors:
    def test_json_caller_gets_generic_message(self, client, conn):
        with patch(
            "src.api.routers.sim.run_offseason", side_effect=RuntimeError(SECRET)
        ):
            r = client.post(f"/leagues/{LEAGUE}/offseason/begin")

        assert r.status_code == 500
        assert r.json() == {"detail": "Something went wrong."}
        assert SECRET not in r.text
        assert "Traceback" not in r.text

    def test_form_post_gets_error_page(self, client, conn):
        with patch(
            "src.api.routers.leagues.start_league", side_effect=RuntimeError(SECRET)
        ):
            r = client.post(
                f"/leagues/{LEAGUE}/start",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )

        assert r.status_code == 500
        assert "text/html" in r.headers["content-type"]
        assert "Something went wrong" in r.text
        assert SECRET not in r.text
        assert "Traceback" not in r.text

    def test_transaction_is_rolled_back(self, client, conn):
        """A failed offseason used to be committed because the route caught
        the error before get_db could see it."""
        with patch("src.api.routers.sim.run_offseason", side_effect=RuntimeError):
            client.post(f"/leagues/{LEAGUE}/offseason/begin")

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_error_is_logged_with_traceback(self, client, conn, caplog):
        with patch(
            "src.api.routers.sim.run_offseason", side_effect=RuntimeError(SECRET)
        ):
            client.post(f"/leagues/{LEAGUE}/offseason/begin")

        (record,) = [r for r in caplog.records if r.exc_info]
        assert SECRET in str(record.exc_info[1])


class TestRuleErrors:
    def test_value_error_message_is_shown(self, client, conn):
        msg = "League must be in 'offseason' state, currently 'playoffs'"
        with patch("src.api.routers.sim.run_offseason", side_effect=ValueError(msg)):
            r = client.post(f"/leagues/{LEAGUE}/offseason/begin")

        assert r.status_code == 400
        assert r.json() == {"detail": msg}
        conn.rollback.assert_called_once()


class TestHttpExceptions:
    def test_forbidden_stays_403(self, client):
        def forbidden():
            raise HTTPException(status_code=403, detail="Not a GM in this league")

        app.dependency_overrides[get_current_gm] = forbidden
        r = client.post(f"/leagues/{LEAGUE}/offseason/begin")

        assert r.status_code == 403
        assert r.json() == {"detail": "Not a GM in this league"}

    def test_page_for_league_im_not_in_goes_to_league_list(self, client):
        """A refresh on a deleted league, or a link to someone else's."""

        def not_a_gm():
            raise NotLeagueGM()

        app.dependency_overrides[get_current_user] = lambda: {"id": "u-1"}
        app.dependency_overrides[get_current_gm] = not_a_gm
        r = client.get(
            f"/leagues/{LEAGUE}/",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

        assert r.status_code == 303
        assert r.headers["location"] == "/leagues/"

    @pytest.mark.parametrize(
        "headers",
        [{"Accept": "application/json"}, {"Accept": "text/html", "HX-Request": "true"}],
    )
    def test_fetch_for_league_im_not_in_stays_403(self, client, headers):
        def not_a_gm():
            raise NotLeagueGM()

        app.dependency_overrides[get_current_gm] = not_a_gm
        r = client.get(f"/leagues/{LEAGUE}/lobby/gms", headers=headers)

        assert r.status_code == 403
        assert r.json() == {"detail": "Not a GM in this league"}

    def test_unauthorized_redirects_home(self, client):
        def unauthorized():
            raise HTTPException(status_code=401, detail="Please log in")

        app.dependency_overrides[get_current_gm] = unauthorized
        r = client.post(f"/leagues/{LEAGUE}/offseason/begin", follow_redirects=False)

        assert r.status_code in (302, 307)
        assert r.headers["location"] == "/"


class TestRosterSaveBody:
    """The body is a RosterSaveRequest, so FastAPI rejects bad JSON with 422."""

    def test_invalid_json_is_rejected(self, client):
        r = client.put(
            f"/leagues/{LEAGUE}/roster/save",
            content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422
        assert r.json()["detail"][0]["type"] == "json_invalid"

    def test_non_object_json_is_rejected(self, client):
        r = client.put(f"/leagues/{LEAGUE}/roster/save", json=["p1", "p2"])
        assert r.status_code == 422
        assert r.json()["detail"][0]["type"] == "model_attributes_type"


class TestLeagueBusy:
    @pytest.mark.parametrize(
        "path",
        ["/sim", "/playoffs/sim", "/offseason/begin"],
    )
    def test_second_sim_gets_409(self, client, conn, path):
        """Another request is already advancing this league."""
        conn.execute.return_value.fetchone.return_value = {"got": False}
        r = client.post(f"/leagues/{LEAGUE}{path}", json={"count": 1})

        assert r.status_code == 409
        assert r.json() == {"detail": "A sim is already running for this league."}


class TestNewLeagueSettings:
    @pytest.fixture
    def user_client(self, client):
        app.dependency_overrides[get_current_user] = lambda: {
            "id": "u-1",
            "display_name": "Alice",
        }
        return client

    @pytest.mark.parametrize(
        "field, value",
        [
            ("mode", "turbo"),
            ("pace_control", "scheduled"),
            ("sim_period_days", "0"),
            ("num_seasons", "0"),
            ("num_seasons", "421"),
        ],
    )
    def test_bad_ready_check_setting_is_rejected(self, user_client, field, value):
        r = user_client.post("/leagues/new", data={"name": "L", field: value})
        assert r.status_code == 400
