# tests/api/test_fa_offers.py
"""Making a free agent an offer (src/api/services/fa_offers.py)."""

from types import SimpleNamespace

import random

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import fa_offers, free_agents, waivers
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player import negotiation as ng


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    theirs = factory.team(city="AI", mascot="Club")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=theirs, league=league, is_ai=True)
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id,
                              away_team_id, completed)
           VALUES (%s, '2026-04-02', %s, %s, %s, 0)""",
        (factory._id(), season.id, mine.id, theirs.id),
    )
    for t in (mine, theirs):
        db_conn.execute(
            """INSERT INTO team_budgets (league_id, team_id, year, cap, budget)
               VALUES (%s, %s, 2026, 900000000, 900000000)""",
            (league.id, t.id),
        )
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        mine=mine,
        theirs=theirs,
        gm=gm,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
    )


@pytest.fixture
def client(lg):
    app.dependency_overrides[get_db] = lambda: lg.db
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    me = {"id": lg.gm.id, "team_id": lg.mine.id}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    yield TestClient(app)
    app.dependency_overrides.clear()


def _free_agent(lg, level=70):
    pid = lg.factory.rated_player(
        lg.theirs, lg.league, level=level, status="free_agent"
    ).id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    return pid


def _ask(lg, pid):
    p = PlayerRepository(lg.db).look_up(pid)
    return fa_offers.asking(lg.db, lg.league.id, p, 2026)


def _calm(monkeypatch):
    """Nobody takes offence."""
    monkeypatch.setattr(ng.Stance, "insulted", lambda *a, **k: False)


def test_his_asking_deal_signs(lg):
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    r = fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, ask.salary, ask.years)
    assert r["result"] == "signed"
    deal = lg.contracts.active(pid, 2026)
    assert (deal["salary"], deal["years"], deal["team_id"]) == (
        ask.salary,
        ask.years,
        lg.mine.id,
    )


def test_a_lowball_gets_a_counter_he_then_signs_at(lg, monkeypatch):
    _calm(monkeypatch)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    r = fa_offers.offer(
        lg.db, lg.league.id, lg.mine.id, pid, int(ask.salary * 0.6), ask.years
    )
    assert r["result"] == "counter"
    c = r["counter"]
    assert int(ask.salary * 0.6) < c["salary"] <= ask.salary
    assert r["hints"]
    assert lg.status.get_status(pid) == "free_agent"
    r = fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, c["salary"], c["years"])
    assert r["result"] == "signed"
    assert lg.contracts.active(pid, 2026)["salary"] == c["salary"]


def test_two_offers_a_week_from_one_club(lg, monkeypatch):
    _calm(monkeypatch)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    low = max(int(ask.salary * 0.5), fa_offers.minimum(lg.db, lg.league.id, 2026))
    for _ in range(ng.OFFERS_PER_WEEK):
        assert (
            fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, low, ask.years)[
                "result"
            ]
            == "counter"
        )
    with pytest.raises(fa_offers.OfferError, match="next week"):
        fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, low, ask.years)
    # His counter still stands.
    want = fa_offers._talks(lg.db, lg.league.id, lg.mine.id, pid)["counter_salary"]
    r = fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, want, ask.years)
    assert r["result"] == "signed"


def test_an_insulted_player_stops_taking_calls_for_two_weeks(lg, monkeypatch):
    monkeypatch.setattr(ng.Stance, "insulted", lambda *a, **k: True)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    low = max(int(ask.salary * 0.5), fa_offers.minimum(lg.db, lg.league.id, 2026))
    r = fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, low, ask.years)
    assert r["result"] == "insulted"
    with pytest.raises(fa_offers.OfferError, match="2 weeks"):
        fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, ask.salary, ask.years)
    week = fa_offers.talk_week(lg.db, lg.league.id)
    assert (
        fa_offers._talks(lg.db, lg.league.id, lg.mine.id, pid)["frozen_until"]
        == week + 2
    )
    # Signing at his asking price still works.
    free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)
    assert lg.status.get_status(pid) == "minors"


def test_never_under_the_minimum(lg):
    pid = _free_agent(lg)
    with pytest.raises(fa_offers.OfferError, match="minimum"):
        fa_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, 500_000, 1)


def test_weeks_go_up_through_the_year():
    weeks = [
        fa_offers.week_of(2026, "season", 0),
        fa_offers.week_of(2026, "season", 7),
        fa_offers.week_of(2026, "playoffs", 190),
        fa_offers.week_of(2026, "offseason"),
        fa_offers.week_of(2027, "draft"),
        fa_offers.week_of(2027, "preseason"),
        fa_offers.week_of(2027, "season", 0),
    ]
    assert weeks == sorted(weeks) and len(set(weeks)) == len(weeks)


def test_ai_openings_follow_the_owner_and_the_gm():
    assert fa_offers.ai_opening(0, 50) == pytest.approx(0.8)
    assert fa_offers.ai_opening(100, 50) == pytest.approx(1.0)
    assert fa_offers.ai_opening(50, 0) < fa_offers.ai_opening(50, 100)


def test_an_ai_team_signs_him_by_negotiating(lg, monkeypatch):
    _calm(monkeypatch)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    import random

    p = PlayerRepository(lg.db).look_up(pid)
    got = fa_offers.ai_offer(
        lg.db, lg.league.id, lg.theirs.id, p, ask, 1e12, 0, 100, random.Random(1), 0
    )
    assert got
    deal = lg.contracts.active(pid, 2026)
    assert deal["team_id"] == lg.theirs.id and deal["salary"] <= ask.salary


def test_offer_endpoints_and_buttons(lg, client, monkeypatch):
    _calm(monkeypatch)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    r = client.get(f"/leagues/{lg.league.id}/free-agents/{pid}/offer")
    assert r.status_code == 200
    body = r.json()
    assert (
        body["ask_salary"] == ask.salary and body["offers_left"] == 2 and body["hints"]
    )
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    assert '"can_offer": true' in html
    html = client.get(f"/leagues/{lg.league.id}/players/{pid}/panel").text
    assert "offerFreeAgent(" in html
    r = client.post(
        f"/leagues/{lg.league.id}/free-agents/{pid}/offer",
        json={"salary": ask.salary, "years": ask.years},
    )
    assert r.status_code == 200 and r.json()["result"] == "signed"


def test_no_offers_while_bids_are_open(lg, client):
    pid = _free_agent(lg)
    lg.db.execute(
        "UPDATE leagues SET state = 'preseason', fa_bidding = TRUE WHERE id = %s",
        (lg.league.id,),
    )
    r = client.get(f"/leagues/{lg.league.id}/free-agents/{pid}/offer")
    assert r.status_code == 422 and "bid" in r.json()["detail"]
    html = client.get(f"/leagues/{lg.league.id}/players/{pid}/panel").text
    assert "offerFreeAgent(" not in html


def test_waivers_first(lg):
    pid = lg.factory.rated_player(lg.theirs, lg.league, level=62).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    lg.contracts.guarantee_teams([lg.theirs.id])
    free_agents.release(lg.db, lg.league.id, lg.theirs.id, pid)
    with pytest.raises(fa_offers.OfferError, match="waivers"):
        fa_offers.preview(lg.db, lg.league.id, lg.mine.id, pid)
    waivers.clear_all(lg.db, lg.league.id)
    assert fa_offers.preview(lg.db, lg.league.id, lg.mine.id, pid)["hints"]


def test_a_cautious_ai_gm_can_walk_away_from_the_counter(lg, monkeypatch):
    _calm(monkeypatch)
    monkeypatch.setattr(fa_offers, "ai_takes_counter", lambda *a: False)
    pid = _free_agent(lg)
    ask = _ask(lg, pid)
    p = PlayerRepository(lg.db).look_up(pid)
    made_room = []
    got = fa_offers.ai_offer(
        lg.db,
        lg.league.id,
        lg.theirs.id,
        p,
        ask,
        1e12,
        0,
        0,
        random.Random(1),
        3,
        before_sign=lambda: made_room.append(1) or True,
    )
    assert not got and not made_room
    assert lg.status.get_status(pid) == "free_agent"
