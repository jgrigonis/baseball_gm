# tests/api/web/test_trades_tab.py
"""The Trades tab, the offer endpoint, and the 40-man minimum on save."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app


@pytest.fixture
def client_for(db_conn, factory):
    def make(mode="blitz", players=0):
        league = factory.league(state="season", mode=mode)
        season = factory.season(year=2025)
        factory.draft(league=league, season=season, state="complete")
        mine = factory.team(city="My", mascot="Team")
        theirs = factory.team(city="AI", mascot="Club")
        for t in (mine, theirs):
            factory.league_season_team(league, season, t)
        gm = factory.gm(team=mine, league=league, is_ai=False)
        factory.gm(team=theirs, league=league, is_ai=True)
        for day, completed in (("2025-04-01", 1), ("2025-04-02", 0), ("2025-04-03", 0)):
            db_conn.execute(
                """INSERT INTO games (id, game_date, season_id, home_team_id,
                                      away_team_id, completed)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (factory._id(), day, season.id, mine.id, theirs.id, completed),
            )
        roster = [factory.rated_player(mine, league, 55) for _ in range(players)]
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        app.dependency_overrides[get_current_gm] = lambda: {
            "id": gm.id,
            "team_id": mine.id,
        }
        return TestClient(app), league, theirs, roster

    yield make
    app.dependency_overrides.clear()


def test_blitz_has_a_trades_tab(client_for):
    client, league, theirs, _ = client_for("blitz")
    html = client.get(f"/leagues/{league.id}/schedule").text
    assert f'href="/leagues/{league.id}/trades"' in html


def test_speed_blitz_has_no_trades_tab(client_for):
    client, league, _, _ = client_for("speed_blitz")
    html = client.get(f"/leagues/{league.id}/schedule").text
    assert f'href="/leagues/{league.id}/trades"' not in html


def test_the_trades_tab_lists_the_other_teams_and_the_deadline(client_for):
    client, league, theirs, _ = client_for("blitz", players=2)
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "Propose trade" in html
    assert "AI Club" in html
    assert "Trade deadline" in html


def test_another_teams_players_for_the_builder(client_for, factory):
    client, league, theirs, _ = client_for("blitz")
    factory.rated_player(theirs, league, 60, name="Target")
    data = client.get(f"/leagues/{league.id}/trades/team/{theirs.id}").json()
    assert [x["last_name"] for x in data["players"]] == ["Target"]


def test_a_broken_offer_comes_back_with_the_reason(client_for):
    client, league, theirs, _ = client_for("blitz")
    r = client.post(
        f"/leagues/{league.id}/trades",
        json={"to_team_id": theirs.id, "give": [], "get": []},
    )
    assert r.status_code == 422
    assert "at least one player" in r.json()["detail"]


def test_the_40_man_needs_at_least_25(client_for):
    client, league, _, roster = client_for("blitz", players=30)
    ids = [p.id for p in roster]
    r = client.put(f"/leagues/{league.id}/roster/save", json={"forty_man": ids[:24]})
    assert r.status_code == 422
    assert "at least 25" in r.json()["detail"]
    r = client.put(f"/leagues/{league.id}/roster/save", json={"forty_man": ids[:25]})
    assert r.status_code == 200


def test_a_team_with_fewer_than_25_players_can_still_save(client_for):
    client, league, _, roster = client_for("blitz", players=20)
    r = client.put(
        f"/leagues/{league.id}/roster/save", json={"forty_man": [p.id for p in roster]}
    )
    assert r.status_code == 200
