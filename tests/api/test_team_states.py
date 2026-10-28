# tests/api/test_team_states.py
"""Team states for a league (src/api/services/team_states.py): inputs from
the rosters and standings, checkpoints, and the standings page."""

import pytest

from src.api.services import team_states
from src.db.repositories.team_state_repo import TeamStateRepository
from src.league import team_state
from src.league.team_state import STATES
from tests.api.test_trades import lg  # noqa: F401

TODAY = "2025-04-04"


@pytest.fixture
def two(lg):  # noqa: F811
    """lg, with my team much stronger and older than theirs, who have kids
    in the minors."""
    for _ in range(9):
        lg.factory.rated_player(lg.mine, lg.league, 72, age=33)
    for _ in range(6):
        lg.factory.rated_player(lg.theirs, lg.league, 62, age=21, status="minors")
    return lg


def test_inputs_rank_the_teams(two):
    i = team_states.gather(two.db, two.league.id, two.season.id)
    mine, theirs = i[two.mine.id], i[two.theirs.id]
    assert mine.rank_now == 0.0 and theirs.rank_now == 1.0
    assert mine.core_age > theirs.core_age
    assert mine.old_share > 0.5
    assert theirs.farm_rank == 0.0
    assert mine.games_back is not None  # in season


def test_current_stores_a_checkpoint_the_first_time(two):
    rows = team_states.current(two.db, two.league.id, two.season.id, TODAY)
    assert set(rows) == {two.mine.id, two.theirs.id}
    assert all(r["state"] in STATES for r in rows.values())
    assert rows[two.mine.id]["state"] == "all-in"  # strong now, old core
    # The next call reads what's stored.
    team_states.current(two.db, two.league.id, two.season.id, TODAY)
    history = TeamStateRepository(two.db).history(two.mine.id, two.season.id)
    assert len(history) == 1


def test_checkpoints_come_weekly(two, monkeypatch):
    # Past the early season, when the first state carries.
    monkeypatch.setattr(team_state, "STANDINGS_MIN_GAMES", 0)
    repo = TeamStateRepository(two.db)

    def count():
        return len(repo.history(two.mine.id, two.season.id))

    team_states.refresh_if_due(two.db, two.league.id, "2025-04-01")
    team_states.refresh_if_due(two.db, two.league.id, "2025-04-05")
    assert count() == 1
    team_states.refresh_if_due(two.db, two.league.id, "2025-04-08")
    assert count() == 2


def test_the_offseason_starts_fresh(two):
    team_states.current(two.db, two.league.id, two.season.id, TODAY)
    two.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (two.league.id,)
    )
    rows = team_states.current(two.db, two.league.id, two.season.id, "2025-10-01")
    assert rows[two.mine.id]["inputs"]["games_back"] is None
    assert not team_states.in_race(rows[two.mine.id])


def test_standings_show_each_front_office(two, client_for):
    team_states.current(two.db, two.league.id, two.season.id, TODAY)
    r = client_for(two).get(f"/leagues/{two.league.id}/standings")
    assert r.status_code == 200
    assert "Direction" in r.text and "All-in" in r.text
    assert "The front office sees an all-in team" in r.text


@pytest.fixture
def client_for(db_conn):
    from fastapi.testclient import TestClient

    from src.api.database import get_db
    from src.api.dependencies import (
        get_current_gm,
        get_current_user,
        get_gm_or_viewer,
    )
    from src.api.main import app

    def make(ctx):
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        gm = {"id": ctx.gm["id"], "team_id": ctx.mine.id}
        app.dependency_overrides[get_current_gm] = lambda: gm
        app.dependency_overrides[get_gm_or_viewer] = lambda: gm
        return TestClient(app, follow_redirects=False)

    yield make

    app.dependency_overrides.clear()
