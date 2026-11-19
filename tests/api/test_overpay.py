# tests/api/test_overpay.py
"""Owners and overpaid players (src/league/overpay.py, Josh 2026-11-19:
"Signing an F rated 19 year old for 30 million didn't even make the Owner
flinch"): the warning before an offer goes in, the owner's word after the
signing, a meddler's veto, and the rare complaint about an overpaid player
already on the roster."""

import json
from types import SimpleNamespace

import pytest

from src.api.services import fa_offers, owner_office
from src.api.services import owners as owner_service
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.owner_repo import OwnerRepository
from src.db.repositories.player_repo import PlayerRepository
from src.league import overpay
from src.player import contracts as ct

M = 1_000_000


# ── The rules ────────────────────────────────────────────────────────────────


def test_how_far_over_counts():
    floor = ct.MIN_SALARY
    # The F-rated 19-year-old at $30M.
    assert overpay.level(30 * M, floor) == "egregious"
    # A fair deal, or a little over, is nothing.
    assert overpay.level(10 * M, 10 * M) is None
    assert overpay.level(14 * M, 10 * M) is None
    # Half again his price and $3M+ more: over.
    assert overpay.level(15 * M, 10 * M) == "over"
    # A big share but small money isn't worth a word.
    assert overpay.level(3 * M, floor) is None
    # Three times and $10M+ more: egregious.
    assert overpay.level(30 * M, 10 * M) == "egregious"
    # Three times but under $10M more: only over.
    assert overpay.level(12 * M, 4 * M) == "over"
    # The lines grow with the cap.
    assert overpay.level(15 * M, 10 * M, scale=2.0) is None


def test_the_warning_names_his_price():
    line = overpay.warning(30 * M, ct.MIN_SALARY)
    assert "$780K" in line and "$30M" in line and "yours will" in line
    assert "watches the money" in overpay.warning(15 * M, 10 * M)
    assert overpay.warning(10 * M, 10 * M) is None


def _owner(weights=None, **traits):
    return {"weights": weights or {}, "traits": traits}


def test_who_minds_an_overpay():
    for o in (_owner(), _owner(spending=95), _owner(meddling=10)):
        assert overpay.cares(o, "egregious")
    assert not overpay.cares(_owner(), "over")
    assert not overpay.cares(_owner(spending=95), "over")
    assert overpay.cares(_owner({"profit": 90}), "over")
    assert overpay.cares(_owner(spending=10), "over")
    assert overpay.cares(_owner(meddling=95), "over")
    assert not overpay.cares(_owner(meddling=95), None)


def test_a_long_egregious_deal_hurts_more_and_spenders_shrug_more():
    o = _owner()
    one = overpay.mood(o, "egregious", 1)
    five = overpay.mood(o, "egregious", 5)
    assert five < one < overpay.mood(o, "over", 1) < 0
    assert overpay.mood(o, "egregious", 20) == overpay.EGREGIOUS_MOST
    assert overpay.mood(_owner(spending=95), "egregious", 1) == one / 2


# ── In a league ──────────────────────────────────────────────────────────────


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
        season=season,
        mine=mine,
        theirs=theirs,
        gm=gm,
    )


def _make_owner(x, weights=None, **traits):
    owner_service.ensure(x.db, x.league.id)
    owner_id = OwnerRepository(x.db).in_league(x.league.id)[x.mine.id]["owner_id"]
    x.db.execute(
        "UPDATE owner_personas SET weights = %s, traits = %s WHERE id = %s",
        (json.dumps(weights or {}), json.dumps(traits), owner_id),
    )


def _free_agent(x, level=10, name="Kid"):
    pid = x.factory.rated_player(
        x.theirs, x.league, level=level, status="free_agent", name=name
    ).id
    x.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    return pid


def _said(x, kind):
    return [
        r["body"]
        for r in x.db.execute(
            "SELECT body FROM owner_messages WHERE gm_id = %s AND kind = %s",
            (x.gm.id, kind),
        ).fetchall()
    ]


def test_overpaying_a_scrub_warns_first_then_the_owner_writes(lg):
    x = lg
    _make_owner(x, meddling=10, spending=50)
    pid = _free_agent(x)
    r = fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 30 * M, 5)
    assert r["result"] == "overpay" and "$30M" in r["warning"]
    # Nothing signed, and no offer used up.
    assert ContractRepository(x.db).active(pid, 2026) is None
    r = fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 30 * M, 5, overpaid_ok=True)
    assert r["result"] == "signed"
    deal = ContractRepository(x.db).active(pid, 2026)
    assert deal["signed_by_gm"] == x.gm.id
    (said,) = _said(x, "overpay")
    assert "Test Kid" in said and "$30M" in said
    # The mood dropped, even before the season's first weekly reading.
    mood = x.db.execute(
        "SELECT mood FROM owner_moods WHERE team_id = %s AND season_id = %s",
        (x.mine.id, x.season.id),
    ).fetchone()["mood"]
    assert mood < 0
    # Once only.
    assert owner_office.reactions(x.db, x.league.id) == 0


def test_a_fair_deal_gets_no_word(lg):
    x = lg
    _make_owner(x, meddling=95, spending=10)
    pid = _free_agent(x)
    ask = fa_offers.asking(x.db, x.league.id, PlayerRepository(x.db).look_up(pid), 2026)
    r = fa_offers.offer(x.db, x.league.id, x.mine.id, pid, ask.salary, ask.years)
    assert r["result"] == "signed"
    assert _said(x, "overpay") == []


def test_a_meddler_vetoes_an_egregious_offer(lg):
    x = lg
    _make_owner(x, meddling=95)
    pid = _free_agent(x)
    with pytest.raises(fa_offers.OfferError) as e:
        fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 30 * M, 5, overpaid_ok=True)
    assert "Test Kid" in str(e.value)
    assert ContractRepository(x.db).active(pid, 2026) is None
    (said,) = _said(x, "overpay_veto")
    assert said == str(e.value)
    # Asking again gives the same answer, kept once.
    with pytest.raises(fa_offers.OfferError):
        fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 30 * M, 5, overpaid_ok=True)
    assert len(_said(x, "overpay_veto")) == 1


def test_a_meddler_allows_a_smaller_overpay_but_says_so(lg):
    x = lg
    _make_owner(x, meddling=95)
    pid = _free_agent(x)
    r = fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 5 * M, 1, overpaid_ok=True)
    assert r["result"] == "signed"
    assert len(_said(x, "overpay")) == 1


def test_a_plain_owner_lets_a_smaller_overpay_pass(lg):
    x = lg
    _make_owner(x, meddling=10, spending=50)
    pid = _free_agent(x)
    r = fa_offers.offer(x.db, x.league.id, x.mine.id, pid, 5 * M, 1, overpaid_ok=True)
    assert r["result"] == "signed"
    assert _said(x, "overpay") == []


def _old_deal(x, pid, salary, signed_by):
    x.db.execute(
        """INSERT INTO player_contracts (player_id, league_id, team_id, kind,
               salary, start_year, years, guaranteed, signed_by_gm)
           VALUES (%s, %s, %s, 'standard', %s, 2025, 4, TRUE, %s)""",
        (pid, x.league.id, x.mine.id, salary, signed_by),
    )


def test_the_owner_complains_once_a_season_about_an_overpaid_player(lg, monkeypatch):
    x = lg
    monkeypatch.setattr(owner_office, "COMPLAINT_GAMES", (0, 0))
    _make_owner(x, meddling=10, spending=50)
    pid = x.factory.rated_player(x.mine, x.league, level=10, name="Bust").id
    _old_deal(x, pid, 30 * M, x.gm.id)
    assert owner_office.reactions(x.db, x.league.id) == 1
    (said,) = _said(x, "overpay")
    assert "Test Bust" in said and "$30M" in said
    assert owner_office.reactions(x.db, x.league.id) == 0


def test_no_complaint_about_the_last_gms_deals(lg, monkeypatch):
    x = lg
    monkeypatch.setattr(owner_office, "COMPLAINT_GAMES", (0, 0))
    _make_owner(x, meddling=10, spending=50)
    pid = x.factory.rated_player(x.mine, x.league, level=10, name="Bust").id
    _old_deal(x, pid, 30 * M, None)
    assert owner_office.reactions(x.db, x.league.id) == 0


def test_no_complaint_before_its_day(lg):
    x = lg
    _make_owner(x, meddling=10, spending=50)
    pid = x.factory.rated_player(x.mine, x.league, level=10, name="Bust").id
    _old_deal(x, pid, 30 * M, x.gm.id)
    # No games played yet: the complaint waits for 30 to 120 games.
    assert owner_office.reactions(x.db, x.league.id) == 0
