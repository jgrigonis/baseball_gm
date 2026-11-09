# tests/api/web/test_lobby.py
"""
The lobby's GM list polls /lobby/gms, so the commissioner sees GMs join and
everyone waiting finds out when the league starts.
"""

import uuid

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


def test_people_link_to_their_gm_profiles(client, db_conn, lobby):
    league, _ = lobby
    username = "joiner_" + uuid.uuid4().hex[:8]
    user_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO users (id, session_token, username, display_name)"
        " VALUES (%s, %s, %s, 'Joiner')",
        (user_id, str(uuid.uuid4()), username),
    )
    db_conn.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, %s, 'Joiner', false)",
        (league.id, user_id),
    )

    r = _gms(client, league)

    assert (
        f'<a href="/gms/{username}" class="gm-link" title="GM profile">Joiner</a>'
        in r.text
    )


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


def test_lobby_links_to_the_team_uniforms_in_a_new_tab(client, lobby):
    league, _ = lobby
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/")

    assert '<a href="/team_uniforms/" target="_blank" rel="noopener"' in r.text


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
        " trades_enabled = false,"
        " reentry_enabled = true WHERE id = %s",
        (league.id,),
    )
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    r = client.get(f"/leagues/{league.id}/")

    # Fourteen settings, plus the GM list's and the settings card's own headers.
    assert r.text.count('class="setting-tip"') == 16
    assert "Speed Blitz" in r.text
    assert "Trades and injuries are off by default" in r.text
    assert "trade with each other." in r.text
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


def test_gm_table_has_no_status_column(client, db_conn, lobby):
    """Nobody can mark themselves away in the lobby, so there's no Status
    column and the hover text doesn't promise one."""
    league, _ = lobby
    _fill(db_conn, league)

    r = _gms(client, league)

    assert "<th>Status</th>" not in r.text
    assert "Away" not in r.text
    assert "Pick another team from the drop down" in r.text


def test_team_picker_leaves_out_ai_gm_names(client, db_conn, lobby):
    """AI GM names made the team drop down too wide, so an AI-held team is
    just marked (AI)."""
    league, gm = lobby
    db_conn.execute("UPDATE leagues SET num_teams = 3 WHERE id = %s", (league.id,))
    db_conn.execute("UPDATE gms SET team_id = NULL WHERE id = %s", (gm.id,))
    personas.fill_lobby(db_conn, league.id)
    ai = personas.lobby_ai_gms(db_conn, league.id)

    picker = (
        _gms(client, league)
        .text.split('class="lobby-team-pick"')[1]
        .split("</select>")[0]
    )

    assert "(AI)" in picker
    for g in ai:
        assert g["display_name"] not in picker


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


def _start_midway(db_conn, factory, league, ai):
    """Where a start job stands once it has dealt the teams and committed,
    with the league still in the lobby: the AI GMs have their teams, and the
    one the start brought in for an open team has no lobby team."""
    from src.db.repositories.sim_job_repo import SimJobRepository

    jobs = SimJobRepository(db_conn)
    jobs.mark_running(jobs.add(league.id, "start", {}, None))
    for i, g in enumerate(ai):
        team = factory.team(city=f"Seat{i}", mascot="Sox")
        db_conn.execute("UPDATE gms SET team_id = %s WHERE id = %s", (team.id, g["id"]))
    db_conn.execute(
        "UPDATE gms SET lobby_city = NULL, lobby_mascot = NULL WHERE id = %s",
        (ai[-1]["id"],),
    )


def test_ai_gms_stay_listed_while_the_league_starts(client, db_conn, factory, lobby):
    """The start gives the AI GMs their teams and commits while the league is
    still in the lobby (setting up the schedule & draft). They stayed on the
    list as 'AI GM (picked at start)' placeholders."""
    league, gm = lobby
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm.id, league.id)
    )
    ai = _fill(db_conn, league)
    _start_midway(db_conn, factory, league, ai)

    r = _gms(client, league)

    assert r.text.count('class="ai-gm"') == 3
    assert 'class="ai-slot"' not in r.text
    assert "picked at start" not in r.text
    for g in ai:
        assert g["display_name"] in r.text
    assert "Seat2 Sox" in r.text  # no lobby team: its real one
    assert "reroll-btn" not in r.text
    assert 'class="lobby-team-pick"' not in r.text


def test_no_reroll_while_the_league_starts(client, db_conn, factory, lobby):
    league, gm = lobby
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm.id, league.id)
    )
    ai = _fill(db_conn, league)
    from src.db.repositories.sim_job_repo import SimJobRepository

    jobs = SimJobRepository(db_conn)
    jobs.mark_running(jobs.add(league.id, "start", {}, None))

    r = client.post(f"/leagues/{league.id}/lobby/gms/{ai[0]['id']}/reroll")

    assert r.status_code == 200
    assert personas.lobby_ai_gms(db_conn, league.id) == ai


def _settings_page(client, league):
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    return client.get(f"/leagues/{league.id}/").text


def _settings_rows(html):
    """The lobby's League Settings rows, as {label: <tr ...> opening tag}."""
    import re

    return {
        label: tag
        for tag, label in re.findall(
            r'(<tr[^>]*>)\s*<td[^>]*>\s*<span class="setting-tip"[^>]*>([^<]+)</span>',
            html,
        )
    }


TIMER_ROWS = ["Pace", "Decision window", "Draft window", "Lineup window"]
# Rows greyed while solo: the timer rows plus Days per sim period.
SOLO_ROWS = TIMER_ROWS + ["Days per sim period"]


def test_timer_settings_are_greyed_out_with_one_human(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute(
        "UPDATE leagues SET pace_control = 'timer' WHERE id = %s", (league.id,)
    )

    rows = _settings_rows(_settings_page(client, league))

    for label in SOLO_ROWS:
        assert 'class="setting-off"' in rows[label], label
        assert "data-needs-humans" in rows[label], label
    assert "setting-off" not in rows["Teams"]


def test_timer_settings_light_up_once_a_second_human_joins(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute(
        "UPDATE leagues SET pace_control = 'timer' WHERE id = %s", (league.id,)
    )
    db_conn.execute(
        "INSERT INTO gms (id, league_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, 'Newcomer', false)",
        (league.id,),
    )

    rows = _settings_rows(_settings_page(client, league))

    for label in SOLO_ROWS:
        assert "setting-off" not in rows[label], label
    assert 'data-humans="2"' in _gms(client, league).text


def test_confirmed_pace_keeps_the_windows_greyed_out(client, db_conn, lobby):
    league, _ = lobby
    db_conn.execute(
        "UPDATE leagues SET pace_control = 'confirmed' WHERE id = %s", (league.id,)
    )
    db_conn.execute(
        "INSERT INTO gms (id, league_id, display_name, is_ai)"
        " VALUES (gen_random_uuid(), %s, 'Newcomer', false)",
        (league.id,),
    )

    rows = _settings_rows(_settings_page(client, league))

    assert "setting-off" not in rows["Pace"]
    for label in TIMER_ROWS[1:]:
        assert 'class="setting-off"' in rows[label], label
        # The lobby's live update leaves these alone.
        assert "data-needs-humans" not in rows[label], label


def test_reentry_sits_below_seasons(client, db_conn, lobby):
    league, _ = lobby

    labels = list(_settings_rows(_settings_page(client, league)))

    assert labels.index("Re-entry") == labels.index("Seasons") + 1
    assert labels.index("Days per sim period") < labels.index("Seasons")


def test_commissioner_controls_sit_above_the_settings(client, db_conn, lobby):
    league, gm = lobby
    _fill(db_conn, league)
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm.id, league.id)
    )
    app.dependency_overrides[get_current_user] = lambda: {"id": None}

    html = client.get(f"/leagues/{league.id}/").text

    assert html.index("Commissioner Controls") < html.index("League Settings</span>")


def _add_humans(db_conn, league, n):
    for i in range(n):
        db_conn.execute(
            "INSERT INTO gms (id, league_id, display_name, is_ai)"
            " VALUES (gen_random_uuid(), %s, %s, false)",
            (league.id, f"Newcomer {i}"),
        )


def _trading_lobby(db_conn, league):
    db_conn.execute(
        "UPDATE leagues SET mode = 'blitz', trades_enabled = true,"
        " trade_vote = true WHERE id = %s",
        (league.id,),
    )


@pytest.mark.parametrize("extra", [0, 1])
def test_trade_vote_is_greyed_out_under_three_humans(client, db_conn, lobby, extra):
    league, _ = lobby
    _trading_lobby(db_conn, league)
    _add_humans(db_conn, league, extra)

    html = _settings_page(client, league)
    row = _settings_rows(html)["Trade vote"]

    assert 'class="setting-off"' in row
    assert 'data-needs-humans="3"' in row
    assert "Only human GMs vote" in html


def test_trade_vote_lights_up_with_three_humans(client, db_conn, lobby):
    league, _ = lobby
    _trading_lobby(db_conn, league)
    _add_humans(db_conn, league, 2)

    rows = _settings_rows(_settings_page(client, league))

    assert "setting-off" not in rows["Trade vote"]
