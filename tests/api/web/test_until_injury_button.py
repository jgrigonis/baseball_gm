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
    assert 'id="sched-stop-injury-box"' in html


def test_speed_blitz_has_no_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "speed_blitz")
    assert "Play Day" in html
    assert "Full Season" in html
    assert 'id="sched-stop-injury-box"' not in html


def test_speed_blitz_with_injuries_turned_on_has_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "speed_blitz", injuries_enabled=True)
    assert 'id="sched-stop-injury-box"' in html


def test_blitz_with_injuries_turned_off_has_no_until_injury(db_conn, factory):
    html = _schedule_html(db_conn, factory, "blitz", injuries_enabled=False)
    assert 'id="sched-stop-injury-box"' not in html


def test_sim_rejects_an_until_injury_count():
    # Until Injury is a run of one-day sims in the browser; the server only
    # takes a day count or "season".
    with pytest.raises(ValidationError):
        SimRequest(count="injury")


def test_blitz_has_trade_stop_boxes(db_conn, factory):
    # Blitz trades, so a Full Season run can be told to play through offers
    # or the deadline.
    html = _schedule_html(db_conn, factory, "blitz")
    assert 'id="sched-stop-offers-box"' in html
    assert 'id="sched-stop-deadline-box"' in html
    assert "sched-ignore-trades-box" not in html


def test_speed_blitz_has_no_trade_stop_boxes(db_conn, factory):
    # No trades, nothing to stop for.
    html = _schedule_html(db_conn, factory, "speed_blitz")
    assert 'id="sched-stop-offers-box"' not in html
    assert 'id="sched-stop-deadline-box"' not in html


def test_no_trade_stop_boxes_past_the_deadline(db_conn, factory, monkeypatch):
    # Past deadline day no team can offer a trade, so the boxes go (and a
    # Full Season run gets its progress bar).
    from src.db.repositories.games_repo import GameRepository
    from src.web import utils

    monkeypatch.setattr(utils, "deadline_date", lambda db, sid: "2025-06-30")
    monkeypatch.setattr(
        GameRepository,
        "get_next_unplayed_date",
        lambda self, sid: {"game_date": "2025-07-02"},
    )
    html = _schedule_html(db_conn, factory, "blitz")
    assert "Full Season" in html
    assert 'id="sched-stop-offers-box"' not in html
    assert 'id="sched-stop-deadline-box"' not in html
    # Deadline day itself still has them: offers can come until it's played.
    monkeypatch.setattr(
        GameRepository,
        "get_next_unplayed_date",
        lambda self, sid: {"game_date": "2025-06-30"},
    )
    on_deadline_day = _schedule_html(db_conn, factory, "blitz")
    assert 'id="sched-stop-offers-box"' in on_deadline_day
    # The button's signature differs, so the page swaps in the new menu
    # after a sim instead of keeping the old boxes until a reload.
    assert _sig(html) != _sig(on_deadline_day)


def _sig(html: str) -> str:
    return html.split('data-sig="', 1)[1].split('"', 1)[0]
