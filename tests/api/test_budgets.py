# tests/api/test_budgets.py
"""The league's payroll cap, owners' budgets and the luxury tax
(src/league/budget.py, src/db/repositories/budget_repo.py), and the
warnings."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import free_agents
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg

M = 1_000_000


# ── Rules ─────────────────────────────────────────────────────────────────────


def test_the_first_cap_is_the_average_payroll_rounded():
    assert bg.first_cap([150 * M, 170 * M, 161 * M]) == 160 * M


def test_the_cap_grows_five_percent_a_season():
    assert bg.grown(160 * M) == 168 * M
    assert bg.grown(160 * M, 2) == 176_400_000


def test_luxury_tax_is_half_of_whats_over_the_cap():
    assert bg.luxury_tax(150 * M, 160 * M) == 0
    assert bg.luxury_tax(170 * M, 160 * M) == 5 * M


def test_a_miser_wants_payroll_under_the_cap_and_a_spender_allows_more():
    assert bg.owner_budget(160 * M, 5) == 146 * M
    assert bg.owner_budget(160 * M, 35) == 160 * M
    assert 5 * M <= bg.leash(160 * M, 50) <= 10 * M
    assert bg.owner_budget(160 * M, 95) == 189 * M


def test_a_warning_only_when_a_move_goes_over():
    # Cap 160, owner allows 170.
    assert bg.warning(150 * M, 160 * M, 170 * M, 5 * M) is None
    assert bg.warning(150 * M, 160 * M, 170 * M, -5 * M) is None
    msg = bg.warning(150 * M, 160 * M, 170 * M, 20 * M)
    assert "$10M over" in msg and "$5M in luxury tax" in msg
    assert "owner" not in msg
    msg = bg.warning(150 * M, 160 * M, 170 * M, 30 * M)
    assert "luxury tax" in msg and "$170M budget" in msg
    assert "already over" in bg.warning(165 * M, 160 * M, 170 * M, 2 * M)


def test_a_misers_budget_warns_under_the_cap_without_tax():
    msg = bg.warning(140 * M, 160 * M, 146 * M, 10 * M)
    assert "luxury tax" not in msg and "$146M budget" in msg


# ── Budgets in a league ───────────────────────────────────────────────────────


@pytest.fixture
def lg(db_conn, factory):
    def make(mode="blitz"):
        league = factory.league(state="season", mode=mode)
        season = factory.season(year=2026)
        factory.league_season(league, season)
        a = factory.team(city="My", mascot="Team")
        b = factory.team(city="AI", mascot="Club")
        for t in (a, b):
            factory.league_season_team(league, season, t)
        gm = factory.gm(team=a, league=league, is_ai=False)
        factory.gm(team=b, league=league, is_ai=True)
        contracts = ContractRepository(db_conn)
        for _ in range(3):
            factory.rated_player(a, league, level=75)
        factory.rated_player(b, league, level=50)
        contracts.sign_unsigned(league.id, 2026)
        return SimpleNamespace(
            db=db_conn,
            factory=factory,
            league=league,
            season=season,
            mine=a,
            theirs=b,
            gm=gm,
            contracts=contracts,
            budgets=BudgetRepository(db_conn),
        )

    return make


def test_every_team_has_the_same_cap(lg):
    x = lg()
    budgets = x.budgets.for_league(x.league.id, 2026)
    pays = [x.contracts.payroll(t.id, 2026) for t in (x.mine, x.theirs)]
    cap = bg.first_cap(pays)
    assert set(budgets) == {x.mine.id, x.theirs.id}
    assert x.budgets.cap(x.league.id, 2026) == cap
    # No owners yet: a middle owner's leash.
    assert budgets[x.mine.id] == budgets[x.theirs.id] == bg.owner_budget(cap, 50)
    caps = x.db.execute(
        "SELECT DISTINCT cap FROM team_budgets WHERE league_id = %s", (x.league.id,)
    ).fetchall()
    assert [r["cap"] for r in caps] == [cap]
    # Stored: asking again gives the same, even after payroll changes.
    x.factory.rated_player(x.theirs, x.league, level=80)
    x.contracts.sign_unsigned(x.league.id, 2026)
    assert x.budgets.for_league(x.league.id, 2026) == budgets


def test_next_seasons_cap_grows_from_this_ones(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    now = x.budgets.cap(x.league.id, 2026)
    x.budgets.for_league(x.league.id, 2027)
    assert x.budgets.cap(x.league.id, 2027) == bg.grown(now)


def test_speed_blitz_has_no_budgets(lg):
    x = lg(mode="speed_blitz")
    assert x.budgets.for_league(x.league.id, 2026) == {}
    assert x.budgets.standing(x.league.id, x.mine.id, 2026) is None


def test_the_tax_is_charged_on_payroll_over_the_cap_not_the_budget(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    # A stingy owner's budget alone doesn't tax anyone.
    x.db.execute("UPDATE team_budgets SET budget = 1000000, cap = 900000000")
    assert x.budgets.assess(x.league.id, 2026)[x.mine.id] == 0
    x.db.execute("UPDATE team_budgets SET cap = 1000000")
    taxes = x.budgets.assess(x.league.id, 2026)
    pay = x.contracts.payroll(x.mine.id, 2026)
    assert taxes[x.mine.id] == bg.luxury_tax(pay, 1_000_000) > 0
    assert (
        x.budgets.tax_paid(x.league.id, x.mine.id)[0]["luxury_tax"]
        == (taxes[x.mine.id])
    )


def test_signing_over_budget_warns_but_is_allowed(lg):
    x = lg()
    pid = x.factory.rated_player(x.theirs, x.league, level=70, status="free_agent").id
    x.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    x.budgets.for_league(x.league.id, 2026)
    x.db.execute("UPDATE team_budgets SET budget = 900000000, cap = 900000000")
    assert (
        free_agents.sign_preview(x.db, x.league.id, x.mine.id, pid)["warning"] is None
    )
    x.db.execute("UPDATE team_budgets SET budget = 1000000, cap = 1000000")
    preview = free_agents.sign_preview(x.db, x.league.id, x.mine.id, pid)
    assert "luxury tax" in preview["warning"]
    free_agents.sign(x.db, x.league.id, x.mine.id, pid)  # not blocked


# ── Views ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client_for():
    def make(x):
        app.dependency_overrides[get_db] = lambda: x.db
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        me = {"id": x.gm.id, "team_id": x.mine.id}
        app.dependency_overrides[get_current_gm] = lambda: me
        app.dependency_overrides[get_gm_or_viewer] = lambda: me
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_the_roster_shows_payroll_against_cap_and_budget(lg, client_for):
    x = lg()
    client = client_for(x)
    budget = x.budgets.budget(x.league.id, x.mine.id, 2026)
    cap = x.budgets.cap(x.league.id, 2026)
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert f"cap {bg.format_salary(cap)}" in html
    assert f"owner {bg.format_salary(budget)}" in html
    x.db.execute("UPDATE team_budgets SET budget = 1000000, cap = 1000000")
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert "over cap · " in html and " tax</span>" in html
    assert "past owner</span>" in html


def test_the_owner_tab_explains_the_cap_and_leash(lg, client_for):
    x = lg()
    _seat(x, x.mine, 95)
    cap = x.budgets.cap(x.league.id, 2026)
    html = client_for(x).get(f"/leagues/{x.league.id}/owner").text
    assert f"payroll cap is <strong>{bg.format_salary(cap)}</strong>" in html
    assert "the same for every team" in html
    assert "over the cap" in html
    pay = x.contracts.payroll(x.mine.id, 2026)
    assert f"Your payroll now: <strong>{bg.format_salary(pay)}</strong>" in html


def test_speed_blitz_roster_shows_just_payroll(lg, client_for):
    x = lg(mode="speed_blitz")
    html = client_for(x).get(f"/leagues/{x.league.id}/roster").text
    assert "Payroll $" in html and "pl-dim" not in html.split("<style>")[0]


# ── Owners set budgets (src/league/finances.py) ───────────────────────────────


def _seat(x, team, spending):
    from src.db.repositories.owner_repo import OwnerRepository
    from src.league import owners

    repo = OwnerRepository(x.db)
    oid = repo.create(
        f"Owner {team.id[:8]} {spending}",
        "",
        "Test",
        owners.clean_weights({}),
        owners.clean_traits({"spending": spending}),
        0,
    )
    repo.seat(x.league.id, team.id, oid, None, 2026)


def test_a_spender_gets_more_than_a_miser(lg):
    x = lg()
    _seat(x, x.mine, 95)
    _seat(x, x.theirs, 5)
    budgets = x.budgets.for_league(x.league.id, 2026)
    pays = [x.contracts.payroll(t.id, 2026) for t in (x.mine, x.theirs)]
    cap = bg.first_cap(pays)
    assert budgets[x.mine.id] == bg.owner_budget(cap, 95) > cap
    assert budgets[x.theirs.id] == bg.owner_budget(cap, 5) < cap
    row = x.db.execute(
        "SELECT revenue, fans_before FROM team_budgets WHERE team_id = %s",
        (x.mine.id,),
    ).fetchone()
    assert row["revenue"] > budgets[x.mine.id] and row["fans_before"] == 50


def test_the_season_end_records_fans_and_profit(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    x.budgets.assess(x.league.id, 2026)
    money = x.budgets.finances(x.league.id, 2026)[x.mine.id]
    assert money["fans_after"] is not None and money["profit"] is not None
    assert money["payroll"] == x.contracts.payroll(x.mine.id, 2026)
    # Next season's cap still grows 5%.
    x.budgets.for_league(x.league.id, 2027)
    assert x.budgets.cap(x.league.id, 2027) == bg.grown(
        x.budgets.cap(x.league.id, 2026)
    )
