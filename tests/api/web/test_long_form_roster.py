# tests/api/web/test_long_form_roster.py
"""
Long Form's Roster tab picks the active (26-man) roster from the 40-man, and
the Lineup tab's red − takes a player off it without leaving the 40-man.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository


@pytest.fixture
def setup(db_conn, factory):
    league = factory.league(state="season", mode="longform")
    season = factory.season()
    factory.league_season(league, season)
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    hitters = [factory.rated_player(team, league, status="26man") for _ in range(16)]
    pitchers = [
        factory.rated_player(team, league, status="26man", pitcher=True)
        for _ in range(14)
    ]
    db_conn.execute(  # 13 hitters + 13 pitchers active, the rest on reserve
        "UPDATE player_status SET status = '40man' WHERE player_id = ANY(%s)",
        ([p.id for p in hitters[13:] + pitchers[13:]],),
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


def _save(client, league, forty, active):
    return client.put(
        f"/leagues/{league.id}/roster/save",
        json={"forty_man": [p.id for p in forty], "active": [p.id for p in active]},
    )


def test_saving_keeps_the_active_roster(client, db_conn, setup):
    league, _, _, _, hitters, pitchers = setup
    active = hitters[1:14] + pitchers[:13]  # swap hitter 0 for hitter 13
    r = _save(client, league, hitters + pitchers, active)
    assert r.status_code == 200, r.text
    status = PlayerStatusRepository(db_conn)
    assert status.get_status(hitters[0].id) == "40man"
    assert status.get_status(hitters[13].id) == "26man"


def test_too_many_pitchers_is_refused(client, setup):
    league, _, _, _, hitters, pitchers = setup
    r = _save(client, league, hitters + pitchers, hitters[:12] + pitchers)
    assert r.status_code == 422
    assert "13 pitchers" in r.json()["detail"]


def test_more_than_26_is_refused(client, setup):
    league, _, _, _, hitters, pitchers = setup
    r = _save(client, league, hitters + pitchers, hitters[:14] + pitchers[:13])
    assert r.status_code == 422
    assert "at most 26" in r.json()["detail"]


def test_fewer_than_25_is_refused(client, setup):
    league, _, _, _, hitters, pitchers = setup
    r = _save(client, league, hitters + pitchers, hitters[:10] + pitchers[:13])
    assert r.status_code == 422
    assert "at least 25" in r.json()["detail"]


def test_active_players_must_be_on_the_40_man(client, setup):
    league, _, _, _, hitters, pitchers = setup
    r = _save(client, league, hitters[1:] + pitchers, hitters[:13] + pitchers[:13])
    assert r.status_code == 422
    assert "40-man" in r.json()["detail"]


def test_september_allows_28_and_14(client, db_conn, setup, factory):
    league, season, team, _, hitters, pitchers = setup
    db_conn.execute(  # the next game day is in September
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
                              completed)
           VALUES (%s, '2025-09-02', %s, %s, %s, 0)""",
        (str(uuid.uuid4()), season.id, team.id, factory.team().id),
    )
    r = _save(client, league, hitters + pitchers, hitters[:14] + pitchers)
    assert r.status_code == 200, r.text
    # It has to be a full 28.
    r = _save(client, league, hitters + pitchers, hitters[:13] + pitchers[:13])
    assert r.status_code == 422
    assert "at least 28" in r.json()["detail"]


def test_red_minus_takes_him_off_the_active_roster(client, db_conn, setup, factory):
    league, season, team, _, hitters, pitchers = setup
    TeamRotationsRepository(db_conn, league.id).set_rotation(
        team.id, season.id, [pitchers[0].id], "2025-04-01"
    )
    r = client.post(f"/leagues/{league.id}/roster/{pitchers[0].id}/reserve")
    assert r.status_code == 200, r.text
    assert PlayerStatusRepository(db_conn).get_status(pitchers[0].id) == "40man"
    assert pitchers[0].id not in {
        x["player_id"]
        for x in TeamRotationsRepository(db_conn, league.id).get_current_rotation(
            team.id, season.id, "2025-05-01"
        )
    }


def test_red_minus_keeps_25_active(client, db_conn, setup):
    league, _, _, _, hitters, _ = setup
    assert (
        client.post(f"/leagues/{league.id}/roster/{hitters[0].id}/reserve").status_code
        == 200
    )
    r = client.post(f"/leagues/{league.id}/roster/{hitters[1].id}/reserve")
    assert r.status_code == 422
    assert "at least 25" in r.json()["detail"]


def test_lineup_tab_shows_only_the_active_roster(client, setup):
    league, _, _, _, hitters, pitchers = setup
    html = client.get(f"/leagues/{league.id}/lineup").text
    assert hitters[0].id in html
    assert hitters[15].id not in html
    assert "const LONG_FORM       = true" in html


def test_roster_tab_shows_the_limits(client, setup):
    league, *_ = setup
    html = client.get(f"/leagues/{league.id}/roster").text
    assert "const LONG_FORM = true" in html
    assert '"pitchers": 13' in html or '"pitchers":13' in html
    assert "Pick Top 26" in html
