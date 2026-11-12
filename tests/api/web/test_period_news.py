# tests/api/web/test_period_news.py
"""Multiplayer: after a period, the ready bar asks /news?team=1 for the
GM's team line on the sim card, like a single player's sim result."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.api.routers import sim as sim_router


@pytest.fixture
def news(db_conn, factory, monkeypatch):
    calls = []

    def fake_my_day(db, league_id, season_id, team_id, game_date):
        calls.append(str(game_date) if game_date else None)
        return {"wins": 3, "losses": 1, "standing": "1st by 1"}

    monkeypatch.setattr(sim_router, "my_day", fake_my_day)

    def get(state, query=""):
        league = factory.league(state=state)
        season = factory.season(year=2025)
        factory.league_season(league, season)
        mine, other = factory.team(), factory.team()
        gm = factory.gm(team=mine, league=league, is_ai=False)
        factory.game({"id": season.id}, {"id": mine.id}, {"id": other.id}, "2025-04-03")
        factory.game({"id": season.id}, {"id": other.id}, {"id": mine.id}, "2025-04-05")
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        app.dependency_overrides[get_current_gm] = lambda: {
            "id": gm.id,
            "team_id": mine.id,
        }
        try:
            return TestClient(app).get(f"/leagues/{league.id}/news{query}").json()
        finally:
            app.dependency_overrides.clear()

    get.calls = calls
    return get


def test_team_line_after_the_last_day_played(news):
    body = news("season", "?team=1")

    assert body["my_team"]["standing"] == "1st by 1"
    assert news.calls == ["2025-04-05"]
    assert body["new_injuries"] == []


def test_plain_news_has_no_team_line(news):
    body = news("season")

    assert "my_team" not in body
    assert news.calls == []


def test_no_team_line_outside_the_regular_season(news):
    body = news("playoffs", "?team=1")

    assert "my_team" not in body


def test_ready_bar_drives_the_sim_card():
    src = open("src/web/templates/dashboard/partials/_ready_bar.html").read()
    assert "simCard.newRun()" in src
    assert "simCard.running(true)" in src
    assert "/news?team=1" in src
