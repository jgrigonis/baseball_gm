# tests/api/web/test_until_injury_button.py
"""The Until Injury play button only shows in leagues that have injuries."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.api.schemas import SimRequest


def _schedule_html(db_conn, factory, mode, injuries_enabled=None):
    league = factory.league(
        state="season", mode=mode, injuries_enabled=injuries_enabled
    )
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    factory.league_season_team(league, season, mine)
    gm = factory.gm(team=mine, league=league, is_ai=False)

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": mine.id,
    }
    try:
        return TestClient(app).get(f"/leagues/{league.id}/schedule").text
    finally:
        app.dependency_overrides.clear()


def test_blitz_has_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "blitz")
    assert "Play Day" in html
    assert "Until Injury" in html


def test_speed_blitz_has_no_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "speed_blitz")
    assert "Play Day" in html
    assert "Full Season" in html
    assert "Until Injury" not in html


def test_speed_blitz_with_injuries_turned_on_has_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "speed_blitz", injuries_enabled=True)
    assert "Until Injury" in html


def test_blitz_with_injuries_turned_off_has_no_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "blitz", injuries_enabled=False)
    assert "Until Injury" not in html


def test_sim_rejects_an_until_injury_count():
    # Until Injury is a run of one-day sims in the browser; the server only
    # takes a day count or "season".
    with pytest.raises(ValidationError):
        SimRequest(count="injury")


def test_blitz_has_ignore_trades_box(db_conn, factory):
    # Blitz trades, so a Full Season run can be told to play through offers
    # and the deadline.
    html = _schedule_html(db_conn, factory, "blitz")
    assert 'id="sched-ignore-trades-box"' in html


def test_speed_blitz_has_no_ignore_trades_box(db_conn, factory):
    # No trades, nothing to ignore.
    html = _schedule_html(db_conn, factory, "speed_blitz")
    assert 'id="sched-ignore-trades-box"' not in html
