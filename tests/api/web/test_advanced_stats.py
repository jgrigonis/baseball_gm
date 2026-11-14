# tests/api/web/test_advanced_stats.py
"""wOBA, wRC+, OPS+, FIP, ERA+ and friends show on the Stats tab, the
Leaders cards, the player panel and the career page."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app

BAT = (
    "bat_ab",
    "bat_hits",
    "bat_doubles",
    "bat_triples",
    "bat_home_runs",
    "bat_walks",
    "bat_strike_outs",
    "bat_hbp",
    "bat_sac_flys",
    "bat_runs",
)
PIT = ("pitch_outs", "pitch_hits", "pitch_earned_runs", "pitch_home_runs",
       "pitch_walks", "pitch_strike_outs", "pitch_hit_batters")  # fmt: skip


def _stats(db, pid, season, team, **cols):
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    db.execute(
        f"INSERT INTO player_season_stats"
        f" (player_id, season_id, team_id, is_postseason, {names})"
        f" VALUES (%s, %s, %s, false, {marks})",
        (pid, season.id, team.id, *cols.values()),
    )


@pytest.fixture
def league(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    team = factory.team(city="My", mascot="Team")
    other = factory.team(city="Other", mascot="Club")
    factory.league_season_team(league, season, team)
    factory.league_season_team(league, season, other)
    gm = factory.gm(team=team, league=league, is_ai=False)
    star = factory.rated_player(team, league, name="Slugger").id
    avg = factory.rated_player(other, league, name="Average").id
    ace = factory.rated_player(team, league, pitcher=True, name="Ace").id
    meh = factory.rated_player(other, league, pitcher=True, name="Meh").id
    games = {"bat_games_played": 100, "bat_games_started": 100}
    _stats(
        db_conn,
        star,
        season,
        team,
        **games,
        **dict(zip(BAT, (400, 130, 30, 3, 30, 60, 80, 5, 5, 80))),
        bat_wpa=3.21,
        bat_re24=30.5,
    )
    _stats(
        db_conn,
        avg,
        season,
        other,
        **games,
        **dict(zip(BAT, (400, 98, 20, 2, 12, 36, 90, 4, 3, 50))),
    )
    pgames = {"pitch_games_played": 20, "pitch_games_started": 20}
    _stats(
        db_conn,
        ace,
        season,
        team,
        **pgames,
        **dict(zip(PIT, (390, 100, 35, 10, 30, 160, 4))),
    )
    _stats(db_conn, meh, season, other, **pgames,
           **dict(zip(PIT, (390, 140, 70, 22, 50, 100, 6))))  # fmt: skip
    return {"league": league, "season": season, "team": team, "gm": gm,
            "star": star, "ace": ace}  # fmt: skip


@pytest.fixture
def client(db_conn, league):
    app.dependency_overrides[get_db] = lambda: db_conn
    gm = {"id": league["gm"].id, "team_id": league["team"].id}
    app.dependency_overrides[get_current_gm] = lambda: gm
    app.dependency_overrides[get_gm_or_viewer] = lambda: gm
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def test_stats_tab_has_the_advanced_columns(client, league):
    lid, sid = league["league"].id, league["season"].id
    r = client.get(
        f"/leagues/{lid}/stats?season_id={sid}", headers={"HX-Request": "true"}
    )
    assert r.status_code == 200
    for key in ("wRC_PLUS", "OPS_PLUS", "wOBA", "BABIP", "FIP", "ERA_PLUS"):
        assert f'"{key}"' in r.text
    assert "label:'wRC+'" in r.text and "label:'ERA+'" in r.text


def test_leaders_have_wrc_plus_and_fip_cards(client, league):
    lid, sid = league["league"].id, league["season"].id
    r = client.get(
        f"/leagues/{lid}/leaders?season={sid}", headers={"HX-Request": "true"}
    )
    assert r.status_code == 200
    for label in ("wOBA", "wRC+", "OPS+", "FIP", "ERA+"):
        assert f">{label}</span>" in r.text


def test_career_page_has_plus_stats(client, league):
    lid = league["league"].id
    r = client.get(f"/leagues/{lid}/players/{league['star']}/career")
    assert r.status_code == 200
    assert ">wRC+</th>" in r.text and ">OPS+</th>" in r.text
    r = client.get(f"/leagues/{lid}/players/{league['ace']}/career")
    assert ">FIP</th>" in r.text and ">ERA+</th>" in r.text


def test_war_shows_on_the_stats_tab_and_leaders(client, league):
    lid, sid = league["league"].id, league["season"].id
    r = client.get(
        f"/leagues/{lid}/stats?season_id={sid}", headers={"HX-Request": "true"}
    )
    assert "label:'WAR'" in r.text and "label:'Def'" in r.text
    assert '"WAR": ' in r.text and '"WAR": null' not in r.text.split("PITCHERS")[0]
    r = client.get(
        f"/leagues/{lid}/leaders?season={sid}", headers={"HX-Request": "true"}
    )
    assert ">WAR (batters)</span>" in r.text and ">WAR (pitchers)</span>" in r.text


def test_season_values_split_hitters_and_pitchers(db_conn, league):
    from src.api.services import season_value

    values = season_value.season_values(db_conn, league["season"].id)
    star, ace = values[league["star"]], values[league["ace"]]
    assert star["hitter"] and star["WAR"] > 0
    assert not ace["hitter"] and ace["WAR"] > 0 and ace["Def"] is None
    assert season_value.pit_war(values, league["star"]) is None
    assert season_value.bat_war(values, league["ace"]) is None


def test_wpa_shows_where_it_was_tracked(client, league):
    lid, sid = league["league"].id, league["season"].id
    r = client.get(
        f"/leagues/{lid}/leaders?season={sid}", headers={"HX-Request": "true"}
    )
    assert ">WPA</span>" in r.text and "+3.21" in r.text
    r = client.get(
        f"/leagues/{lid}/stats?season_id={sid}", headers={"HX-Request": "true"}
    )
    assert '"WPA": 3.21' in r.text
    # Lines from before WPA was tracked show none rather than 0.
    assert '"WPA": null' in r.text
    r = client.get(f"/leagues/{lid}/players/{league['star']}/career")
    assert ">WPA</th>" in r.text and "+3.21" in r.text
