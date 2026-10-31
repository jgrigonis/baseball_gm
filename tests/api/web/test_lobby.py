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
from src.api.services import personas


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
    assert 'hx-trigger="every 3s' in r.text


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
        "UPDATE leagues SET mode = 'speed_blitz', injuries_enabled = false,"
        " reentry_enabled = true WHERE id = %s",
        (league.id,),
    )
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/")

    # Eleven settings, plus the GM list's and the settings card's own headers.
    assert r.text.count('class="setting-tip"') == 13
    assert "Speed Blitz" in r.text
    assert "no trades. Injuries start off" in r.text
    assert "Off: nobody gets hurt" in r.text
    assert "Total teams in the league" in r.text
    assert "<td>Enabled</td>" in r.text


def _fill(db_conn, league, num_teams=4):
    db_conn.execute(
        "UPDATE leagues SET num_teams = %s WHERE id = %s", (num_teams, league.id)
    )
    personas.fill_lobby(db_conn, league.id)
    return personas.lobby_ai_gms(db_conn, league.id)


def test_picked_ai_gms_are_listed_by_name(client, db_conn, lobby):
    league, _ = lobby
    ai = _fill(db_conn, league)

    r = _gms(client, league)

    assert r.text.count('class="ai-gm"') == 3
    assert 'class="ai-slot"' not in r.text
    assert "1 human · 3 AI" in r.text
    for g in ai:
        assert g["display_name"] in r.text
        assert f"/leagues/{league.id}/personas/{g['persona_id']}" in r.text


def test_only_the_commissioner_sees_reroll(client, db_conn, lobby):
    league, gm = lobby
    _fill(db_conn, league)

    assert "reroll-btn" not in _gms(client, league).text

    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm.id, league.id)
    )
    assert _gms(client, league).text.count("reroll-btn") == 3


def test_commissioner_rerolls_an_ai_gm(client, db_conn, lobby):
    league, gm = lobby
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm.id, league.id)
    )
    ai = _fill(db_conn, league)

    r = client.post(f"/leagues/{league.id}/lobby/gms/{ai[0]['id']}/reroll")

    assert r.status_code == 200
    after = personas.lobby_ai_gms(db_conn, league.id)
    assert after[0]["persona_id"] != ai[0]["persona_id"]
    assert after[0]["display_name"] in r.text


def test_others_cannot_reroll(client, db_conn, lobby):
    league, _ = lobby
    ai = _fill(db_conn, league)

    r = client.post(f"/leagues/{league.id}/lobby/gms/{ai[0]['id']}/reroll")

    assert r.status_code == 403
    assert personas.lobby_ai_gms(db_conn, league.id) == ai


def test_lobby_persona_card_opens(client, db_conn, lobby):
    league, _ = lobby
    ai = _fill(db_conn, league)
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/personas/{ai[0]['persona_id']}")

    assert r.status_code == 200
    assert ai[0]["display_name"] in r.text


def test_each_gm_shows_the_team_they_were_dealt(client, db_conn, lobby):
    league, gm = lobby
    db_conn.execute("UPDATE leagues SET num_teams = 3 WHERE id = %s", (league.id,))
    db_conn.execute("UPDATE gms SET team_id = NULL WHERE id = %s", (gm.id,))
    personas.fill_lobby(db_conn, league.id)
    rows = db_conn.execute(
        "SELECT lobby_city, lobby_mascot FROM gms WHERE league_id = %s",
        (league.id,),
    ).fetchall()

    r = _gms(client, league)

    assert len(rows) == 3
    for row in rows:
        assert f"{row['lobby_city']} {row['lobby_mascot']}" in r.text
    assert r.text.count('class="team-badge') >= 3


def test_a_person_picks_their_team_from_their_row(client, db_conn, lobby):
    league, gm = lobby
    db_conn.execute("UPDATE leagues SET num_teams = 3 WHERE id = %s", (league.id,))
    db_conn.execute("UPDATE gms SET team_id = NULL WHERE id = %s", (gm.id,))
    personas.fill_lobby(db_conn, league.id)
    ai = personas.lobby_ai_gms(db_conn, league.id)[0]
    before = db_conn.execute(
        "SELECT lobby_city, lobby_mascot FROM gms WHERE id = %s", (gm.id,)
    ).fetchone()

    page = _gms(client, league)
    assert 'class="lobby-team-pick"' in page.text
    assert page.text.count('class="lobby-team-pick"') == 1

    r = client.post(
        f"/leagues/{league.id}/lobby/team",
        data={"team": f"{ai['lobby_city']}|{ai['lobby_mascot']}"},
    )

    assert r.status_code == 200
    me = db_conn.execute(
        "SELECT lobby_city, lobby_mascot FROM gms WHERE id = %s", (gm.id,)
    ).fetchone()
    them = db_conn.execute(
        "SELECT lobby_city, lobby_mascot FROM gms WHERE id = %s", (ai["id"],)
    ).fetchone()
    assert (me["lobby_city"], me["lobby_mascot"]) == (
        ai["lobby_city"],
        ai["lobby_mascot"],
    )
    assert dict(them) == dict(before)
