# tests/api/test_resign_offers.py
"""Negotiating a re-sign on the Expiring Deals tab
(src/api/services/resign_offers.py)."""

import dataclasses
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import ai_free_agents, free_agents, offseason_fa, resign_offers
from src.api.services.resign_offers import ResignOfferError
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.player import contracts as ct
from src.player import happiness as hp
from src.player import negotiation as ng


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="offseason", mode="blitz")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    ai = factory.team(city="Ai", mascot="Club")
    for t in (mine, ai):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=ai, league=league, is_ai=True)
    BudgetRepository(db_conn).for_league(league.id, 2026)
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        mine=mine,
        ai=ai,
        gm=gm,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
    )


@pytest.fixture(autouse=True)
def roomy(monkeypatch):
    monkeypatch.setattr(BudgetRepository, "refusal", lambda *a, **k: None)
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: float("inf"))
    monkeypatch.setattr(offseason_fa, "_room", lambda *a: float("inf"))
    monkeypatch.setattr(offseason_fa, "_bank", lambda *a: 0)
    monkeypatch.setattr(hp, "refuses_to_resign", lambda *a: None)


@pytest.fixture
def client(lg):
    app.dependency_overrides[get_db] = lambda: lg.db
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    me = {"id": lg.gm.id, "team_id": lg.mine.id}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    yield TestClient(app)
    app.dependency_overrides.clear()


def _expiring(lg, start, years, level=75, team=None):
    """A player whose deal ends with 2026: 6+ seasons is a veteran."""
    team = team or lg.mine
    pid = lg.factory.rated_player(team, lg.league, level=level, status="40man").id
    lg.contracts.insert_deal(
        pid, lg.league.id, team.id, ct.Deal(5_000_000, years, "standard"), start
    )
    return pid


def _person(monkeypatch, **kw):
    """Give every expiring player these traits (nobody else calling, not
    Easygoing unless asked)."""
    real = resign_offers.stance

    def fake(*a, **k):
        return dataclasses.replace(
            real(*a, **k),
            **(
                {
                    "callers": 0,
                    "easygoing": False,
                    "fit": 0.0,
                    "money": 0,
                    "ego": 50,
                    "loyalty": 50,
                    "star": False,
                }
                | kw
            ),
        )

    monkeypatch.setattr(resign_offers, "stance", fake)


def _row(lg, pid):
    return next(
        r
        for r in offseason_fa.expiring_view(lg.db, lg.league.id, lg.mine.id)
        if r["player_id"] == pid
    )


def _offer(lg, pid, salary, years):
    return resign_offers.offer(lg.db, lg.league.id, lg.mine.id, pid, salary, years)


def test_his_asking_deal_is_agreed_and_re_signs_at_it(lg, monkeypatch):
    _person(monkeypatch)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    r = _offer(lg, pid, ask["ask_salary"], ask["ask_years"])
    assert r["result"] == "signed"
    row = _row(lg, pid)
    assert row["choice"] == "resign" and row["agreed"] and row["fate"] == "resign"


def test_a_fair_try_gets_a_counter_and_an_agreed_deal_replaces_his_price(
    lg, monkeypatch
):
    _person(monkeypatch, temper=50, loyalty=50)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)["ask_salary"]
    years = _row(lg, pid)["ask_years"]
    r = _offer(lg, pid, int(ask * 0.88), years)
    assert r["result"] == "counter"
    c = r["counter"]
    assert int(ask * 0.88) < c["salary"] <= ask
    assert r["hints"]
    # Taking his answer doesn't use an offer, and the agreed deal is his
    # price on the tab, the room line and when the offseason runs.
    r = _offer(lg, pid, c["salary"], c["years"])
    assert r["result"] == "signed"
    row = _row(lg, pid)
    assert row["salary"] == c["salary"] and row["agreed"]
    assert row["ask_salary"] == ask
    offseason_fa.close_window(lg.db, lg.league.id)
    new = lg.contracts.active(pid, 2027)
    assert (new["salary"], new["years"]) == (c["salary"], c["years"])


def test_re_sign_pays_his_asking_price_again(lg, monkeypatch):
    _person(monkeypatch)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    more = int(ask["ask_salary"] * 1.3)
    assert _offer(lg, pid, more, ask["ask_years"])["result"] == "signed"
    assert _row(lg, pid)["salary"] == more
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "resign")
    row = _row(lg, pid)
    assert row["salary"] == ask["ask_salary"] and not row["agreed"]


def test_three_offers_in_the_window(lg, monkeypatch):
    _person(monkeypatch, easygoing=True)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    low = int(ask["ask_salary"] * 0.86)
    for _ in range(ng.OFFERS_PER_WINDOW):
        r = _offer(lg, pid, low, ask["ask_years"])
        assert r["result"] == "counter"
    with pytest.raises(ResignOfferError, match="3 offers"):
        _offer(lg, pid, low, ask["ask_years"])
    # His answer still stands.
    c = r["counter"]
    assert _offer(lg, pid, c["salary"], c["years"])["result"] == "signed"


def test_a_lowball_leaves_a_grudge_but_easygoing_shrugs(lg, monkeypatch):
    _person(monkeypatch, temper=80, loyalty=20, easygoing=False)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    monkeypatch.setattr(ng.Stance, "home_insulted", lambda *a: False)
    r = _offer(lg, pid, int(ask["ask_salary"] * 0.8), ask["ask_years"])
    assert r["result"] == "counter" and r["stung"]
    happy = HappinessRepository(lg.db, lg.league.id)
    assert happy.grudge(pid, lg.mine.id, 2026) > 0

    _person(monkeypatch, temper=80, easygoing=True)
    calm = _expiring(lg, 2021, 6)
    ask = _row(lg, calm)
    r = _offer(lg, calm, int(ask["ask_salary"] * 0.8), ask["ask_years"])
    assert not r["stung"]
    assert happy.grudge(calm, lg.mine.id, 2026) == 0


def test_an_insulted_veteran_raises_his_price(lg, monkeypatch):
    _person(monkeypatch, temper=95)
    monkeypatch.setattr(ng.Stance, "refuse_chance", lambda self: 0.0)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    r = _offer(lg, pid, int(ask["ask_salary"] * 0.5), ask["ask_years"])
    assert r["result"] == "insulted" and "price is up" in r["line"]
    row = _row(lg, pid)
    assert row["ask_salary"] > ask["ask_salary"]
    assert row["no_offer"] and "done talking" in row["no_offer"]
    with pytest.raises(ResignOfferError, match="done talking"):
        _offer(lg, pid, ask["ask_salary"], ask["ask_years"])
    # He still re-signs at his new price.
    offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "resign")
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(pid, 2027)["salary"] == row["ask_salary"]


def test_an_insulted_veteran_can_refuse_and_cant_come_back(lg, monkeypatch):
    _person(monkeypatch, temper=95, loyalty=5)
    monkeypatch.setattr(ng.Stance, "refuse_chance", lambda self: 1.0)
    pid = _expiring(lg, 2021, 6)
    ask = _row(lg, pid)
    r = _offer(lg, pid, int(ask["ask_salary"] * 0.5), ask["ask_years"])
    assert r["result"] == "refused"
    row = _row(lg, pid)
    assert row["refuses"] == "insulted" and row["fate"] == "go"
    with pytest.raises(offseason_fa.OffseasonFAError, match="insulted"):
        offseason_fa.choose(lg.db, lg.league.id, lg.mine.id, pid, "resign")
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.status.get_status(pid) == "free_agent"
    assert free_agents.refused(lg.db, lg.league.id, lg.mine.id, pid, 2027)


def test_a_player_under_control_cant_walk_but_holds_it_against_you(lg, monkeypatch):
    _person(monkeypatch, temper=95)
    pid = _expiring(lg, 2024, 3)  # 3 seasons: tendered, can't walk
    ask = _row(lg, pid)
    r = _offer(lg, pid, int(ask["ask_salary"] * 0.5), ask["ask_years"])
    assert r["result"] == "insulted" and "can't leave" in r["line"]
    row = _row(lg, pid)
    assert row["refuses"] is None and row["ask_salary"] == ask["ask_salary"]
    assert HappinessRepository(lg.db, lg.league.id).grudge(pid, lg.mine.id, 2026) > 0
    offseason_fa.close_window(lg.db, lg.league.id)
    assert lg.contracts.active(pid, 2027)["start_year"] == 2027


def test_the_dialog_warns_in_words(lg, monkeypatch):
    _person(monkeypatch, temper=80, loyalty=20)
    vet = _expiring(lg, 2021, 6)
    young = _expiring(lg, 2024, 3)
    p = resign_offers.preview(lg.db, lg.league.id, lg.mine.id, vet)
    assert "refuse to re-sign" in p["warnings"][0]
    assert "He has a short fuse." in p["warnings"]
    assert "He doesn't owe you any loyalty." in p["warnings"]
    assert p["offers_left"] == ng.OFFERS_PER_WINDOW
    p = resign_offers.preview(lg.db, lg.league.id, lg.mine.id, young)
    assert "can't leave" in p["warnings"][0]
    assert not any(ch.isdigit() for line in p["warnings"] + p["hints"] for ch in line)


def test_no_offers_to_arbitration_or_minimum_players_or_out_of_season(lg):
    pid = _expiring(lg, 2021, 6)
    lg.db.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (lg.league.id,))
    with pytest.raises(ResignOfferError, match="offseason"):
        resign_offers.preview(lg.db, lg.league.id, lg.mine.id, pid)
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason', mode = 'speed_blitz' WHERE id = %s",
        (lg.league.id,),
    )
    with pytest.raises(ResignOfferError, match="no contracts"):
        resign_offers.preview(lg.db, lg.league.id, lg.mine.id, pid)


def test_no_offer_reasons():
    base = dict(
        refuses=None,
        arb_season=None,
        scale=1.0,
        ask=ct.Deal(5_000_000, 2, "standard"),
        talks_closed=False,
    )
    assert offseason_fa.no_offer(base) is None
    assert "Arbitration" in offseason_fa.no_offer(base | {"arb_season": 4})
    assert "minimum" in offseason_fa.no_offer(
        base | {"ask": ct.Deal(ct.MIN_SALARY, 1, "standard")}
    )
    assert "any price" in offseason_fa.no_offer(base | {"refuses": "fame"})


def test_endpoints_and_the_offer_button(lg, client, monkeypatch):
    _person(monkeypatch, easygoing=True)
    pid = _expiring(lg, 2021, 6)
    url = f"/leagues/{lg.league.id}/players/{pid}/expiring/offer"
    r = client.get(url)
    assert r.status_code == 200 and r.json()["warnings"]
    ask = r.json()
    r = client.post(url, json={"salary": ask["ask_salary"], "years": ask["ask_years"]})
    assert r.status_code == 200
    d = r.json()
    assert d["result"] == "signed" and d["rows"][pid]["agreed"]
    page = client.get(f"/leagues/{lg.league.id}/expiring")
    assert 'data-c="offer"' in page.text and "offerExpiring" in page.text


def test_a_grudge_takes_off_his_mood_and_fades():
    from src.db.repositories.happiness_repo import grudge_left

    assert grudge_left(0.1, 0, ng.GRUDGE_WEEKS) == pytest.approx(0.1)
    assert grudge_left(0.1, ng.GRUDGE_WEEKS // 2, ng.GRUDGE_WEEKS) == pytest.approx(
        0.05
    )
    assert grudge_left(0.1, ng.GRUDGE_WEEKS, ng.GRUDGE_WEEKS) == 0
