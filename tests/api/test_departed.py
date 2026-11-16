# tests/api/test_departed.py
"""Players who've left a team, tagged on the Stats tab
(src/api/view_models/departed.py)."""

from types import SimpleNamespace

import pytest

from src.api.view_models.departed import attach_departures, departures


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season")
    s26 = factory.season(year=2026)
    factory.league_season(league, s26)
    a = factory.team(city="Madrid", mascot="Conquistadors")
    b = factory.team(city="Boston", mascot="Beacons")
    c = factory.team(city="Tokyo", mascot="Captains")
    for t in (a, b, c):
        factory.league_season_team(league, s26, t)
    return SimpleNamespace(db=db_conn, f=factory, league=league, s26=s26, a=a, b=b, c=c)


def _move(lg, pid, team):
    """Takes him off every team, then onto `team` (None: a free agent)."""
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    if team:
        lg.db.execute(
            "INSERT INTO team_players (team_id, player_id) VALUES (%s, %s)",
            (team.id, pid),
        )


def _trade(lg, pid, gave, got, on, at="2026-03-01 00:00+00"):
    oid = lg.f._id()
    lg.db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
               to_team_id, status, created_on, created_at, decided_at)
           VALUES (%s, %s, %s, %s, %s, 'accepted', %s, %s, %s)""",
        (oid, lg.league.id, lg.s26.id, gave.id, got.id, on, at, at),
    )
    lg.db.execute(
        "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)"
        " VALUES (%s, %s, %s)",
        (oid, pid, gave.id),
    )


def _waive(lg, pid, team, on, status, claimed_by=None, at="2026-04-01 00:00+00"):
    lg.db.execute(
        """INSERT INTO waivers (league_id, player_id, from_team_id, placed_on,
               status, claimed_by, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (lg.league.id, pid, team.id, on, status,
         claimed_by.id if claimed_by else None, at),
    )  # fmt: skip


def _gone(lg, *pids):
    return departures(lg.db, lg.league.id, lg.a.id, pids)


def test_players_still_on_the_team_are_not_tagged(lg):
    pid = lg.f.rated_player(lg.a, lg.league).id
    assert _gone(lg, pid) == {}


def test_traded_away(lg):
    pid = lg.f.rated_player(lg.a, lg.league).id
    _trade(lg, pid, lg.a, lg.b, "2026-07-14")
    _move(lg, pid, lg.b)
    assert _gone(lg, pid) == {pid: {"tag": "Traded", "tip": "Traded to Boston, Jul 14"}}


def test_traded_by_the_other_side_of_the_offer(lg):
    # Boston made the offer; Madrid sent him.
    pid = lg.f.rated_player(lg.a, lg.league).id
    oid = lg.f._id()
    lg.db.execute(
        """INSERT INTO trade_offers (id, league_id, season_id, from_team_id,
               to_team_id, status, created_on, created_at)
           VALUES (%s, %s, %s, %s, %s, 'accepted', '2026-06-02', NOW())""",
        (oid, lg.league.id, lg.s26.id, lg.b.id, lg.a.id),
    )
    lg.db.execute(
        "INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)"
        " VALUES (%s, %s, %s)",
        (oid, pid, lg.a.id),
    )
    _move(lg, pid, lg.b)
    assert _gone(lg, pid)[pid]["tip"] == "Traded to Boston, Jun 2"


def test_traded_then_moved_on(lg):
    pid = lg.f.rated_player(lg.a, lg.league).id
    _trade(lg, pid, lg.a, lg.b, "2026-07-14")
    _move(lg, pid, lg.c)
    assert _gone(lg, pid)[pid]["tip"] == "Traded to Boston, Jul 14; now with Tokyo"


def test_released_and_claimed(lg):
    pid = lg.f.rated_player(lg.a, lg.league).id
    _waive(lg, pid, lg.a, "2026-06-03", "claimed", claimed_by=lg.b)
    _move(lg, pid, lg.b)
    assert _gone(lg, pid) == {
        pid: {"tag": "Released", "tip": "Released Jun 3, claimed by Boston"}
    }


def test_released_on_waivers_cleared_and_signed(lg):
    on, cleared, signed = (lg.f.rated_player(lg.a, lg.league).id for _ in range(3))
    _waive(lg, on, lg.a, "2026-06-03", "open")
    _waive(lg, cleared, lg.a, "2026-06-03", "cleared")
    _waive(lg, signed, lg.a, "2026-06-03", "cleared")
    _move(lg, on, None)
    _move(lg, cleared, None)
    _move(lg, signed, lg.c)
    gone = _gone(lg, on, cleared, signed)
    assert gone[on]["tip"] == "Released Jun 3, on waivers"
    assert gone[cleared]["tip"] == "Released Jun 3; now a free agent"
    assert gone[signed]["tip"] == "Released Jun 3; signed with Tokyo"


def test_latest_move_wins(lg):
    # Traded away, traded back, then released.
    pid = lg.f.rated_player(lg.a, lg.league).id
    _trade(lg, pid, lg.a, lg.b, "2026-05-01", at="2026-03-01 00:00+00")
    _waive(lg, pid, lg.a, "2026-08-01", "cleared", at="2026-05-01 00:00+00")
    _move(lg, pid, None)
    assert _gone(lg, pid)[pid]["tag"] == "Released"


def test_retired_and_left(lg):
    retired, left = (lg.f.rated_player(lg.a, lg.league).id for _ in range(2))
    lg.db.execute(
        """INSERT INTO player_retirements (player_id, league_id, season_id,
               former_team_id) VALUES (%s, %s, %s, %s)""",
        (retired, lg.league.id, lg.s26.id, lg.a.id),
    )
    _move(lg, retired, None)
    _move(lg, left, lg.c)
    gone = _gone(lg, retired, left)
    assert gone[retired] == {"tag": "Retired", "tip": "Retired"}
    assert gone[left] == {"tag": "Left", "tip": "Now with Tokyo"}


def test_attach_marks_every_line(lg):
    stay, go = (lg.f.rated_player(lg.a, lg.league).id for _ in range(2))
    _trade(lg, go, lg.a, lg.b, "2026-07-14")
    _move(lg, go, lg.b)
    bat = [{"player_id": stay}, {"player_id": go}]
    field = [{"player_id": go}]
    assert attach_departures(lg.db, lg.league.id, lg.a.id, bat, field) == 1
    assert bat[0]["departed"] is None
    assert bat[1]["departed"] == "Traded"
    assert field[0]["departed_tip"] == "Traded to Boston, Jul 14"


def test_stats_tab_tags_departed_players(db_conn, lg):
    from fastapi.testclient import TestClient

    from src.api.database import get_db
    from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
    from src.api.main import app

    gm = lg.f.gm(team=lg.a, league=lg.league, is_ai=False)
    stay = lg.f.rated_player(lg.a, lg.league, name="Stayer").id
    go = lg.f.rated_player(lg.a, lg.league, name="Goner").id
    for pid in (stay, go):
        db_conn.execute(
            """INSERT INTO player_season_stats (player_id, season_id, team_id,
                   is_postseason, bat_games_played, bat_ab, bat_hits)
               VALUES (%s, %s, %s, false, 10, 30, 9)""",
            (pid, lg.s26.id, lg.a.id),
        )
    _trade(lg, go, lg.a, lg.b, "2026-07-14")
    _move(lg, go, lg.b)

    me = {"id": gm.id, "team_id": lg.a.id}
    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    try:
        client = TestClient(app, follow_redirects=False)
        url = f"/leagues/{lg.league.id}/stats?season_id={lg.s26.id}"
        r = client.get(url, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert 'id="btn-departed"' in r.text
    assert '"departed": "Traded"' in r.text
    assert '"departed_tip": "Traded to Boston, Jul 14"' in r.text
