# tests/api/web/test_solo_settings.py
"""
The commissioner of a one-person league can change most settings from the
League page once it has started: the name, seasons, days per sim period,
schedule, injuries, trades, draft pick trades and re-entry. They lock again
once a second person joins (src/api/services/league_settings.py).
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league.trades.draft_picks import Pick


@pytest.fixture
def league(db_conn, factory):
    """A solo league in season 2 of 10: one human commissioner, one AI GM."""
    league = factory.league(state="season", trades_enabled=True)
    db_conn.execute(
        "UPDATE leagues SET num_teams = 2, num_seasons = 10, sim_period_days = 3,"
        " weighted_schedule = TRUE, pick_trades = TRUE WHERE id = %s",
        (league.id,),
    )
    seasons = [factory.season(year=y) for y in (2025, 2026)]
    for s in seasons:
        factory.league_season(league, s)
    mine = factory.team(city="Boston", mascot="Beans")
    theirs = factory.team(city="Chicago", mascot="Wind")
    human = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=theirs, league=league)
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s",
        (human.id, league.id),
    )
    return league, human, mine, theirs, seasons[-1]


@pytest.fixture
def client(db_conn, league):
    gm = league[1]
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id}
    app.dependency_overrides[get_gm_or_viewer] = lambda: {"id": gm.id, "team_id": None}
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _form(**overrides):
    form = {
        "name": "Renamed",
        "num_seasons": "12",
        "sim_period_days": "5",
        "weighted_schedule": "false",
        "injuries_enabled": "true",
        "trades_enabled": "true",
        "pick_trades": "true",
        "reentry_enabled": "true",
    }
    form.update(overrides)
    return {k: v for k, v in form.items() if v is not None}


def _row(db_conn, league_id):
    return LeagueRepository(db_conn).get_by_id(league_id)


def test_solo_commissioner_sees_the_edit_form(client, league):
    lg = league[0]

    html = client.get(f"/leagues/{lg.id}/league").text

    assert 'id="solo-edit-open"' in html
    assert f'action="/leagues/{lg.id}/league/settings"' in html
    # Seasons slide from the one being played (2), not 1, to unlimited.
    assert "data-choices='[2, 3," in html and ", 60, 0]'" in html
    assert 'name="sim_period_days" id="ss-days" value="3" min="1" max="30"' in html
    assert 'type="checkbox" name="weighted_schedule" value="true" checked' in html


def test_saves_every_setting(client, db_conn, league):
    lg = league[0]

    r = client.post(
        f"/leagues/{lg.id}/league/settings",
        data=_form(injuries_enabled=None, reentry_enabled=None),
    )

    assert r.status_code == 303
    assert r.headers["location"].endswith("/league?saved=1")
    row = _row(db_conn, lg.id)
    assert row["name"] == "Renamed"
    assert row["num_seasons"] == 12
    assert row["sim_period_days"] == 5
    assert row["weighted_schedule"] is False
    assert row["injuries_enabled"] is False
    assert row["reentry_enabled"] is False
    assert row["trades_enabled"] and row["pick_trades"]


def test_seasons_cant_go_below_the_current_one(client, db_conn, league):
    lg = league[0]

    r = client.post(f"/leagues/{lg.id}/league/settings", data=_form(num_seasons="1"))

    assert "settings_error=" in r.headers["location"]
    assert _row(db_conn, lg.id)["num_seasons"] == 10
    # The season being played can be the last one.
    client.post(f"/leagues/{lg.id}/league/settings", data=_form(num_seasons="2"))
    assert _row(db_conn, lg.id)["num_seasons"] == 2


def test_after_the_playoffs_the_next_season_is_the_fewest(client, db_conn, league):
    lg = league[0]
    db_conn.execute("UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.id,))

    client.post(f"/leagues/{lg.id}/league/settings", data=_form(num_seasons="2"))
    assert _row(db_conn, lg.id)["num_seasons"] == 10

    client.post(f"/leagues/{lg.id}/league/settings", data=_form(num_seasons="3"))
    assert _row(db_conn, lg.id)["num_seasons"] == 3


def test_locks_once_a_second_person_joins(client, db_conn, factory, league):
    lg = league[0]
    factory.gm(team=factory.team(city="Denver", mascot="Peaks"), league=lg, is_ai=False)

    html = client.get(f"/leagues/{lg.id}/league").text
    assert 'id="solo-edit-open"' not in html

    r = client.post(f"/leagues/{lg.id}/league/settings", data=_form())
    assert "settings_error=" in r.headers["location"]
    assert _row(db_conn, lg.id)["name"] != "Renamed"


def test_only_the_commissioner(client, db_conn, factory, league):
    lg = league[0]
    other = factory.gm(team=factory.team(), league=lg)
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (other.id, lg.id)
    )

    assert 'id="solo-edit-open"' not in client.get(f"/leagues/{lg.id}/league").text
    client.post(f"/leagues/{lg.id}/league/settings", data=_form())
    assert _row(db_conn, lg.id)["name"] != "Renamed"


def _offer(db_conn, factory, league, items):
    lg, _, mine, theirs, season = league
    return TradeRepository(db_conn).create_offer(
        lg.id, season.id, theirs.id, mine.id, None, "2026-05-01", items
    )


def test_trades_off_expires_open_offers(client, db_conn, factory, league):
    lg, _, mine, theirs, _ = league
    offer = _offer(
        db_conn,
        factory,
        league,
        [(factory.player_row().id, theirs.id), (factory.player_row().id, mine.id)],
    )

    client.post(f"/leagues/{lg.id}/league/settings", data=_form(trades_enabled=None))

    assert _row(db_conn, lg.id)["trades_enabled"] is False
    assert TradeRepository(db_conn).get(offer)["status"] == "expired"


def test_pick_trades_off_calls_off_offers_with_picks(client, db_conn, factory, league):
    lg, _, mine, theirs, _ = league
    with_pick = _offer(
        db_conn,
        factory,
        league,
        [(Pick(2027, 1, theirs.id).id, theirs.id), (factory.player_row().id, mine.id)],
    )
    players_only = _offer(
        db_conn,
        factory,
        league,
        [(factory.player_row().id, theirs.id), (factory.player_row().id, mine.id)],
    )

    client.post(f"/leagues/{lg.id}/league/settings", data=_form(pick_trades=None))

    trades = TradeRepository(db_conn)
    assert trades.get(with_pick)["status"] == "void"
    assert trades.get(players_only)["status"] == "pending"
