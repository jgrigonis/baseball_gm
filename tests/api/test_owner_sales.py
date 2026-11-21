"""Owners in the red warn their GM, and past the sale line sell the team
(src/api/services/owner_sales.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.services import owner_sales
from src.api.services.news import events
from src.api.services.news.names import Names
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg

M = 1_000_000


def test_the_sale_line_is_half_a_cap_in_the_red():
    assert bg.sale_line(180 * M) == -90 * M
    assert not bg.must_sell(-90 * M, 180 * M)
    assert bg.must_sell(-91 * M, 180 * M)
    assert not bg.must_sell(-91 * M, 0)


@pytest.fixture
def x(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    other = factory.team(city="AI", mascot="Club")
    for t in (mine, other):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=other, league=league, is_ai=True)
    factory.rated_player(mine, league, level=60)
    factory.rated_player(other, league, level=60)
    ContractRepository(db_conn).sign_unsigned(league.id, 2026)
    for oid, name, spending in (("sell1", "Broke Cat", 50), ("buy1", "New Money", 80)):
        db_conn.execute(
            """INSERT INTO owner_personas (id, name, archetype, bio, weights, traits, chance)
               VALUES (%s, %s, 'The Tycoon', '', '{}', %s, 0)
               ON CONFLICT (id) DO NOTHING""",
            (oid, name, f'{{"spending": {spending}}}'),
        )
    db_conn.execute(
        """INSERT INTO team_owners (league_id, team_id, owner_id, since_year)
           VALUES (%s, %s, 'sell1', 2026)""",
        (league.id, mine.id),
    )
    budgets = BudgetRepository(db_conn)
    budgets.for_league(league.id, 2026)
    budgets.assess(league.id, 2026)
    return SimpleNamespace(
        db=db_conn, league=league, season=season, mine=mine, gm=gm,
        budgets=budgets, cap=budgets.cap(league.id, 2026),
    )  # fmt: skip


def _set_balance(x, balance):
    bank = x.budgets.banks(x.league.id)[x.mine.id]
    start = bank["start"] + balance - bank["balance"]
    x.db.execute(
        "UPDATE team_owners SET bank_start = %s WHERE league_id = %s AND team_id = %s",
        (start, x.league.id, x.mine.id),
    )
    assert x.budgets.banks(x.league.id)[x.mine.id]["balance"] == balance
    return start


def _messages(x):
    return {
        r["key"].split(":")[0]: r
        for r in x.db.execute(
            "SELECT key, kind, body FROM owner_messages WHERE league_id = %s AND team_id = %s",
            (x.league.id, x.mine.id),
        ).fetchall()
    }


def test_a_bank_in_the_red_warns_the_gm(x):
    _set_balance(x, -x.cap // 5)
    assert owner_sales.settle(x.db, x.league.id, x.season.id, 2026) == []
    msgs = _messages(x)
    assert msgs["red"]["kind"] == "bank"
    assert f"{bg.format_salary(x.cap // 5)} in the red" in msgs["red"]["body"]
    assert bg.format_salary(-bg.sale_line(x.cap)) in msgs["red"]["body"]
    owner = x.db.execute(
        "SELECT owner_id FROM team_owners WHERE league_id = %s AND team_id = %s",
        (x.league.id, x.mine.id),
    ).fetchone()
    assert owner["owner_id"] == "sell1"


def test_a_bank_in_the_black_says_nothing(x):
    _set_balance(x, 5 * M)
    assert owner_sales.settle(x.db, x.league.id, x.season.id, 2026) == []
    assert _messages(x) == {}


def test_past_the_line_the_owner_sells_to_a_fresh_bank(x):
    # Only the buyer can be drawn (rolled back after the test).
    x.db.execute(
        "UPDATE owner_personas SET chance = CASE id WHEN 'buy1' THEN 50 ELSE 0 END"
    )
    debt = bg.sale_line(x.cap) - M
    old_start = _set_balance(x, debt)
    sales = owner_sales.settle(x.db, x.league.id, x.season.id, 2026)
    assert [s["new_owner_id"] for s in sales] == ["buy1"]
    # Only once a season.
    assert owner_sales.settle(x.db, x.league.id, x.season.id, 2026) == []
    row = x.db.execute(
        """SELECT owner_id, since_year, bank_start, bank_year FROM team_owners
           WHERE league_id = %s AND team_id = %s""",
        (x.league.id, x.mine.id),
    ).fetchone()
    fresh = bg.starting_bank(x.cap, 80)
    assert dict(row) == {
        "owner_id": "buy1", "since_year": 2027, "bank_start": fresh, "bank_year": 2027,
    }  # fmt: skip
    bank = x.budgets.banks(x.league.id)[x.mine.id]
    assert bank["balance"] == fresh and bank["change"] == 0
    msgs = _messages(x)
    assert "red" not in msgs
    assert msgs["sold"]["kind"] == "sale"
    assert "Broke Cat has sold me" in msgs["sold"]["body"]
    assert "You keep your job" in msgs["sold"]["body"]
    sale = x.budgets.sales(x.league.id, x.mine.id)[0]
    assert (sale["old_bank_start"], sale["debt"], sale["new_bank"]) == (
        old_start,
        debt,
        fresh,
    )

    # The bank history runs the old owner's bank to the sale, then the new.
    x.budgets.for_league(x.league.id, 2027)
    history = {r["year"]: r for r in x.budgets.history(x.league.id, x.mine.id)}
    assert history[2026]["bank_before"] == old_start
    assert history[2026]["bank_after"] == debt
    assert history[2027]["bank_before"] == fresh
    # The new budget follows the buyer's Spending with a bank right where
    # it started.
    budget = x.budgets.for_league(x.league.id, 2027)[x.mine.id]
    cap2 = x.budgets.cap(x.league.id, 2027)
    leash = bg.owner_budget(cap2, 80, 0)
    assert budget == leash + bg.standard_front_office(cap2) + bg.luxury_tax(leash, cap2)

    events.owner_sales(
        x.db, Names(x.db, x.league.id), x.league.id, x.season.id, "2026-10-31"
    )
    story = x.db.execute(
        "SELECT headline, body FROM league_news WHERE league_id = %s AND key LIKE 'sold:%%'",
        (x.league.id,),
    ).fetchone()
    assert "sold to New Money" in story["headline"]
    assert "Broke Cat has sold" in story["body"]


def test_the_budget_tab_warns_when_the_bank_is_in_the_red(x):
    from fastapi.testclient import TestClient

    from src.api.database import get_db
    from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
    from src.api.main import app

    _set_balance(x, -x.cap // 5)
    me = {"id": x.gm.id, "team_id": x.mine.id}
    app.dependency_overrides[get_db] = lambda: x.db
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    try:
        html = TestClient(app).get(f"/leagues/{x.league.id}/budget").text
    finally:
        app.dependency_overrides.clear()
    assert "Your owner is in the red" in html
    assert f"more than {bg.format_salary(-bg.sale_line(x.cap))} in the red" in html
