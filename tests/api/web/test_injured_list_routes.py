# tests/api/web/test_injured_list_routes.py
"""Long Form's Roster tab puts hurt players on the injured list and brings
them back; the IL pill reminds people."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.api.services import next_move
from src.db.repositories.player_status_repo import PlayerStatusRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season", mode="longform")
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    hitters = [factory.rated_player(team, league, status="26man") for _ in range(14)]
    pitchers = [
        factory.rated_player(team, league, status="26man", pitcher=True)
        for _ in range(13)
    ]
    db_conn.execute(
        "UPDATE player_status SET status = '40man' WHERE player_id = %s",
        (hitters[13].id,),
    )
    # The next game day is May 10.
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
                              completed)
           VALUES (%s, '2025-05-10', %s, %s, %s, 0)""",
        (str(uuid.uuid4()), season.id, team.id, factory.team().id),
    )
    db_conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, return_date)
           VALUES (%s, %s, '2025-06-20')""",
        (hitters[0].id, league.id),
    )
    return league, season, team, gm, hitters, pitchers


@pytest.fixture
def client(db_conn, setup):
    _, _, team, gm, _, _ = setup
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id, "team_id": team.id}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_place_and_the_roster_save_rules(client, db_conn, setup):
    league, _, _, _, hitters, pitchers = setup
    r = client.post(
        f"/leagues/{league.id}/roster/{hitters[0].id}/il", json={"kind": 10}
    )
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == 10
    assert PlayerStatusRepository(db_conn).get_status(hitters[0].id) == "40man"

    every = [p.id for p in hitters + pitchers]
    # He can't be on the active roster...
    r = client.put(
        f"/leagues/{league.id}/roster/save",
        json={"forty_man": every, "active": every[:13] + [p.id for p in pitchers][:0]},
    )
    assert r.status_code == 422 and "injured list" in r.json()["detail"]
    # ...or leave the 40-man.
    r = client.put(
        f"/leagues/{league.id}/roster/save",
        json={"forty_man": every[1:], "active": every[1:]},
    )
    assert r.status_code == 422 and "stay on the 40-man" in r.json()["detail"]


def test_healthy_players_cant_go_on(client, setup):
    league, _, _, _, hitters, _ = setup
    r = client.post(
        f"/leagues/{league.id}/roster/{hitters[1].id}/il", json={"kind": 10}
    )
    assert r.status_code == 422
    assert "Only injured" in r.json()["detail"]


def test_activate_waits_for_the_days(client, db_conn, setup):
    league, _, _, _, hitters, _ = setup
    client.post(f"/leagues/{league.id}/roster/{hitters[0].id}/il", json={"kind": 10})
    r = client.post(f"/leagues/{league.id}/roster/{hitters[0].id}/activate")
    assert r.status_code == 422 and "until" in r.json()["detail"]
    # Healed and past his days: back on the active roster if there's room.
    db_conn.execute(
        "UPDATE player_injuries SET return_date = '2025-05-01' WHERE player_id = %s",
        (hitters[0].id,),
    )
    db_conn.execute(
        "UPDATE injured_list SET eligible_on = '2025-05-09' WHERE player_id = %s",
        (hitters[0].id,),
    )
    r = client.post(f"/leagues/{league.id}/roster/{hitters[0].id}/activate")
    assert r.status_code == 200, r.text
    assert r.json()["to"] == "26man"


def test_roster_tab_offers_the_il(client, setup):
    league, _, _, _, hitters, _ = setup
    html = client.get(f"/leagues/{league.id}/roster").text
    assert '"il_kinds": [10, 60]' in html or '"il_kinds":[10,60]' in html
    assert 'const TODAY     = "2025-05-10"' in html


def test_the_il_pill_reminds_people(client, setup):
    league, *_ = setup
    html = client.get(f"/leagues/{league.id}/lineup").text
    assert "🩹 IL (1)" in html


def test_il_pill_shape():
    ctx = {"league_id": "L", "il_due": {"place": ["a"], "activate": ["b", "c"]}}
    pill = next_move._il_pill(ctx, "standings")
    assert pill["label"] == "🩹 IL (3)"
    assert pill["href"] == "/leagues/L/roster"
    assert "1 hurt on your active roster and 2 ready" in pill["title"]
    assert next_move._il_pill(ctx, "roster") is None
    assert next_move._il_pill({"league_id": "L"}, "standings") is None
