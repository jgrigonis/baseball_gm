# tests/api/web/test_next_move_button.py
"""The next-move button sits in the top bar of every league page, and the
shell reloads it for the page it lands on."""

from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app


def _get(db_conn, factory, state, *paths, joined=False):
    league = factory.league(state=state, mode="blitz")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    factory.league_season_team(league, season, mine)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    if joined:
        # A second human GM: the league runs by ready-check.
        theirs = factory.team(city="Their", mascot="Team")
        factory.league_season_team(league, season, theirs)
        other = factory.gm(team=theirs, league=league, is_ai=False)
        for i, g in enumerate((gm, other)):
            uid = f"{league.id}-u{i}"
            db_conn.execute(
                "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
                (uid, uid, f"GM {i}"),
            )
            db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (uid, g.id))

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    me = {"id": gm.id, "team_id": mine.id}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    try:
        client = TestClient(app)
        return [client.get(p.format(id=league.id)).text for p in paths]
    finally:
        app.dependency_overrides.clear()


def test_play_day_is_in_the_top_bar_on_leaders_and_standings(db_conn, factory):
    pages = ("/leagues/{id}/leaders", "/leagues/{id}/standings")
    for html in _get(db_conn, factory, "season", *pages):
        assert 'id="next-move"' in html and 'id="sched-play-btn"' in html
        assert "▶ Play Day" in html and 'id="sched-stop-btn"' in html


def test_one_play_button_on_the_schedule(db_conn, factory):
    (html,) = _get(db_conn, factory, "season", "/leagues/{id}/schedule")
    assert html.count('id="sched-play-btn"') == 1


def test_the_button_reloads_for_the_page(db_conn, factory):
    away, there = _get(
        db_conn,
        factory,
        "playoffs",
        "/leagues/{id}/next-move?page=standings",
        "/leagues/{id}/next-move?page=playoffs",
    )
    assert "Go to Playoffs" in away and 'href="/leagues/' in away
    assert "Sim Playoff Day" in there and 'data-fn="simPlayoffs"' in there
    assert "<html" not in there  # just the button


def test_the_button_says_when_a_gm_joined(db_conn, factory):
    """The shell reloads the whole page when this flips: a solo page has no
    ready-check script, so its I'm ready button would do nothing."""
    url = "/leagues/{id}/next-move?page=standings"
    (solo,) = _get(db_conn, factory, "season", url)
    (shared,) = _get(db_conn, factory, "season", url, joined=True)
    assert 'data-mp="0"' in solo and 'id="sched-play-btn"' in solo
    assert 'data-mp="1"' in shared and 'onclick="readyToggle()"' in shared
