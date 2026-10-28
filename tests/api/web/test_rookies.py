# tests/api/web/test_rookies.py
"""A rookie is a player the league drafted who, in the regular seasons before
this one, has no more than 130 at bats and 50 innings pitched. Rookies get an
(R) after their name."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository


def _player(db, league, first, last):
    pid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO players (id, first_name, last_name, bats, throws, position, league_id)"
        " VALUES (%s, %s, %s, 'R', 'R', 'of', %s)",
        (pid, first, last, league.id),
    )
    return pid


def _stats(db, player_id, season, team, postseason=False, **cols):
    cols = {"bat_games_played": 10, **cols}
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    db.execute(
        f"INSERT INTO player_season_stats"
        f" (player_id, season_id, team_id, is_postseason, {names})"
        f" VALUES (%s, %s, %s, %s, {marks})",
        (player_id, season.id, team.id, postseason, *cols.values()),
    )


def _pick(db, draft, n, gm, team, player_id):
    db.execute(
        """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)
           VALUES (%s, %s, 1, %s, %s, %s)""",
        (draft.id, n, gm.id, team.id, player_id),
    )


@pytest.fixture
def league(db_conn, factory):
    """A league in its 2026 season. Its 2025 and 2026 drafts are done."""
    league = factory.league(state="season")
    past = factory.season(year=2025)
    current = factory.season(year=2026)
    factory.league_season(league, past)
    factory.league_season(league, current)
    team = factory.team(city="My", mascot="Team")
    factory.league_season_team(league, past, team)
    factory.league_season_team(league, current, team)
    gm = factory.gm(team=team, league=league, is_ai=False)

    p = {
        "full": _player(db_conn, league, "Full", "Season"),  # 200 AB in 2025
        "cup": _player(db_conn, league, "Cup", "Ofcoffee"),  # 40 AB, 200 in playoffs
        "arm": _player(db_conn, league, "Short", "Arm"),  # 49 IP in 2025
        "ace": _player(db_conn, league, "Big", "Arm"),  # 60 IP in 2025
        "new": _player(db_conn, league, "New", "Kid"),  # drafted for 2026
        "vet": _player(db_conn, league, "Old", "Vet"),  # on the starting roster
    }
    draft_2025 = factory.draft(league=league, season=past, state="complete")
    for n, key in enumerate(("full", "cup", "arm", "ace"), 1):
        _pick(db_conn, draft_2025, n, gm, team, p[key])
    draft_2026 = factory.draft(league=league, season=current, state="complete")
    _pick(db_conn, draft_2026, 1, gm, team, p["new"])

    _stats(db_conn, p["full"], past, team, bat_ab=200)
    _stats(db_conn, p["cup"], past, team, bat_ab=40)
    _stats(db_conn, p["cup"], past, team, postseason=True, bat_ab=200)
    _stats(db_conn, p["arm"], past, team, pitch_outs=147)
    _stats(db_conn, p["ace"], past, team, pitch_outs=180)
    _stats(db_conn, p["vet"], past, team, bat_ab=10)
    for key in ("full", "cup", "new", "vet"):
        _stats(db_conn, p[key], current, team, bat_ab=50, bat_hits=15)

    return {"league": league, "past": past, "current": current, "gm": gm,
            "team": team, "players": p}  # fmt: skip


@pytest.fixture
def client(db_conn, league):
    app.dependency_overrides[get_db] = lambda: db_conn
    gm = {"id": league["gm"].id, "team_id": league["team"].id}
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: gm
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_rookies_this_season(db_conn, league):
    p = league["players"]
    ids = PlayerSeasonStatsRepository(db_conn).get_rookie_ids(
        league["league"].id, league["current"].id
    )
    # Postseason at bats don't count; 49 innings is under the limit.
    assert ids == {p["cup"], p["arm"], p["new"]}


def test_rookies_last_season(db_conn, league):
    p = league["players"]
    ids = PlayerSeasonStatsRepository(db_conn).get_rookie_ids(
        league["league"].id, league["past"].id
    )
    # Every 2025 draftee was a rookie in 2025; the 2026 pick wasn't drafted yet.
    assert ids == {p["full"], p["cup"], p["arm"], p["ace"]}


def test_leaders_mark_rookies(client, league):
    lid, sid = league["league"].id, league["current"].id
    r = client.get(f"/leagues/{lid}/leaders?season={sid}")
    assert r.status_code == 200
    tag = '<span class="rookie-tag" title="Rookie">(R)</span>'
    assert "New Kid" + tag in r.text
    assert "Cup Ofcoffee" + tag in r.text
    assert "Full Season" in r.text and "Full Season" + tag not in r.text
    assert "Old Vet" in r.text and "Old Vet" + tag not in r.text


@pytest.mark.parametrize("tab", ["roster", "lineup", "stats", "trades"])
def test_tabs_that_draw_names_in_js_get_the_rookie_ids(client, league, tab):
    lid = league["league"].id
    r = client.get(f"/leagues/{lid}/{tab}", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "window.ROOKIE_IDS" in r.text
    assert league["players"]["new"] in r.text.split("window.ROOKIE_IDS", 1)[1][:400]
