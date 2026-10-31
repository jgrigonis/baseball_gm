# tests/api/web/test_welcome.py
"""
The welcome screen: once per GM when a league starts, before the draft, it
shows their new team (plans/welcome-screen.md).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.view_models import welcome as wv
from src.db.repositories.gm_repo import GMRepository


@pytest.fixture
def league(db_conn, factory):
    """A new league waiting on its first draft: a human GM's Boston Beans,
    an AI GM's Chicago Wind, and opening day in Chicago."""
    league = factory.league(state="draft")
    season = factory.season(year=2025)
    draft = factory.draft(league=league, season=season)
    boston = factory.team(city="Boston", mascot="Beans")
    chicago = factory.team(city="Chicago", mascot="Wind")
    factory.draft_order(draft, [chicago, boston])
    human = factory.gm(team=boston, league=league, is_ai=False)
    factory.gm(team=chicago, league=league)
    for team, level in ((boston, 70), (chicago, 50)):
        for i in range(9):
            factory.rated_player(
                team, league, level=level, age=22 + 2 * i, name=f"H{i}"
            )
        for i in range(5):
            factory.rated_player(team, league, level=level, pitcher=True, name=f"P{i}")
    factory.game({"id": season.id}, {"id": chicago.id}, {"id": boston.id})
    return league, human, boston


@pytest.fixture
def client(db_conn, league):
    _, gm, team = league
    me = {"id": gm.id, "team_id": team.id}
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_a_new_league_opens_on_the_welcome_screen_once(client, league):
    lg, _, _ = league

    first = client.get(f"/leagues/{lg.id}/")
    assert first.headers["location"] == f"/leagues/{lg.id}/welcome"

    page = client.get(f"/leagues/{lg.id}/welcome")
    assert page.status_code == 200
    assert "Welcome to the Boston Beans" in page.text
    assert f'href="/leagues/{lg.id}/draft"' in page.text

    again = client.get(f"/leagues/{lg.id}/")
    assert again.headers["location"] == f"/leagues/{lg.id}/draft"


def test_welcome_page_shows_the_team(client, league):
    lg, _, _ = league

    html = client.get(f"/leagues/{lg.id}/welcome").text

    assert "Your stars" in html and "Your colors" not in html
    assert html.count('class="wl-star-name"') == 5
    assert "1st of 2" in html  # Boston's 70s beat Chicago's 50s everywhere
    assert "at the <b>Chicago Wind</b>" in html
    assert "2025-04-01" in html
    assert "2<span" in html and "of 2" in html  # picks second
    assert "Chicago Wind" in html.split("Teams to beat")[1]


def test_later_seasons_skip_the_welcome(client, db_conn, factory, league):
    lg, _, _ = league
    factory.league_season(lg, factory.season(year=2026))

    r = client.get(f"/leagues/{lg.id}/")

    assert r.headers["location"] == f"/leagues/{lg.id}/draft"


def test_the_roster_links_back_to_it(client, db_conn, league):
    lg, gm, _ = league
    GMRepository(db_conn).mark_welcomed(gm.id)

    assert client.get(f"/leagues/{lg.id}/").headers["location"].endswith("/draft")
    assert client.get(f"/leagues/{lg.id}/welcome").status_code == 200


# ── View model pieces ─────────────────────────────────────────────────────────


def test_scouting_report_ranks_and_verdict():
    scores = {
        "me": {"lineup": 70, "rotation": 40, "bullpen": 55, "defense": 60},
        "b": {"lineup": 60, "rotation": 60, "bullpen": 60, "defense": 60},
        "c": {"lineup": 50, "rotation": 70, "bullpen": 50, "defense": 50},
    }

    report = wv.scouting_report("me", scores)

    ranks = {a["key"]: a["rank"] for a in report["areas"]}
    assert ranks == {"lineup": 1, "rotation": 3, "bullpen": 2, "defense": 1}
    assert report["verdict"] == (
        "Built around its lineup (1st of 3), but the rotation (3rd of 3) needs help."
    )


def test_ordinals():
    assert [wv.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
    ]


# ── The getting-started bar ───────────────────────────────────────────────────


def test_setup_bar_stays_until_the_roster_is_saved(client, db_conn, league):
    lg, _, team = league
    assert 'id="setup-bar"' in client.get(f"/leagues/{lg.id}/league").text

    ids = [
        r["player_id"]
        for r in db_conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s", (team.id,)
        ).fetchall()
    ]
    r = client.put(f"/leagues/{lg.id}/roster/save", json={"forty_man": ids})
    assert r.status_code == 200

    assert 'id="setup-bar"' not in client.get(f"/leagues/{lg.id}/league").text


def test_running_the_draft_ends_the_setup_bar(client, db_conn, league):
    lg, _, _ = league
    db_conn.execute(
        "UPDATE drafts SET state = 'complete' WHERE league_id = %s", (lg.id,)
    )

    html = client.get(f"/leagues/{lg.id}/league").text

    assert 'id="setup-bar"' not in html


def test_persona_cards_link_back_to_where_they_came_from(client, db_conn, league):
    lg, _, _ = league
    persona = db_conn.execute("SELECT id FROM gm_personas LIMIT 1").fetchone()
    if not persona:
        pytest.skip("no personas in the library")
    url = f"/leagues/{lg.id}/personas/{persona['id']}"

    assert f'href="/leagues/{lg.id}/welcome"' in client.get(url + "?back=welcome").text
    assert "Back to the League page" in client.get(url).text
    assert "Back to the League page" in client.get(url + "?back=evil").text
