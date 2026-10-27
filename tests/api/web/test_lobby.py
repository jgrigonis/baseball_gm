# tests/api/web/test_lobby.py
"""
The lobby's GM list polls /lobby/gms, so the commissioner sees GMs join and
everyone waiting finds out when the league starts.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app


@pytest.fixture
def lobby(db_conn, factory):
    league = factory.league(state="lobby")
    gm = factory.gm(league=league, is_ai=False)
    return league, gm


@pytest.fixture
def client(db_conn, lobby):
    _, gm = lobby
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm.id}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _gms(client, league):
    return client.get(f"/leagues/{league.id}/lobby/gms")


def test_lists_a_gm_who_just_joined(client, db_conn, factory, lobby):
    league, _ = lobby
    db_conn.execute(
        "INSERT INTO gms (id, league_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, 'Newcomer', false)",
        (league.id,),
    )

    r = _gms(client, league)

    assert r.status_code == 200
    assert "Newcomer" in r.text
    assert 'hx-trigger="every 3s"' in r.text


def test_started_league_redirects_the_page(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (league.id,))

    r = _gms(client, league)

    assert r.headers["HX-Redirect"] == f"/leagues/{league.id}/"


def test_lobby_page_polls_the_gm_list(client, lobby):
    league, _ = lobby
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/")

    assert r.status_code == 200
    assert f'hx-get="/leagues/{league.id}/lobby/gms"' in r.text


def test_open_slots_show_as_ai_gms(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))

    r = _gms(client, league)

    assert r.text.count('class="ai-slot"') == 3
    assert "1 human · 3 AI" in r.text


def test_a_gm_who_joins_takes_an_ai_slot(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))
    db_conn.execute(
        "INSERT INTO gms (id, league_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, 'Newcomer', false)",
        (league.id,),
    )

    r = _gms(client, league)

    assert r.text.count('class="ai-slot"') == 2
    assert "2 human · 2 AI" in r.text


def test_lobby_settings_explain_themselves_on_hover(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute(
        "UPDATE leagues SET mode = 'speed_blitz', reentry_enabled = true WHERE id = %s",
        (league.id,),
    )
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/")

    # Ten settings, plus the GM list's and the settings card's own headers.
    assert r.text.count('class="setting-tip"') == 12
    assert "Speed Blitz" in r.text
    assert "no injuries or trades" in r.text
    assert "Total teams in the league" in r.text
    assert "<td>Enabled</td>" in r.text
