# tests/api/test_budgets.py
"""Team budgets and the luxury tax (src/league/budget.py,
src/db/repositories/budget_repo.py), and the warnings."""

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


def test_the_first_budget_is_the_average_payroll_rounded():
    assert bg.first_budget([150 * M, 170 * M, 161 * M]) == 160 * M


def test_budgets_grow_five_percent_a_season():
    assert bg.grown(160 * M) == 168 * M
    assert bg.grown(160 * M, 2) == 176_400_000


def test_luxury_tax_is_half_of_whats_over():
    assert bg.luxury_tax(150 * M, 160 * M) == 0
    assert bg.luxury_tax(170 * M, 160 * M) == 5 * M


def test_a_warning_only_when_a_move_goes_over():
    assert bg.warning(150 * M, 160 * M, 5 * M) is None
    assert bg.warning(150 * M, 160 * M, -5 * M) is None
    msg = bg.warning(150 * M, 160 * M, 20 * M)
    assert "$10M over" in msg and "$5M in luxury tax" in msg
    assert "already over" in bg.warning(170 * M, 160 * M, 2 * M)


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


def test_every_team_starts_with_the_same_budget(lg):
    x = lg()
    budgets = x.budgets.for_league(x.league.id, 2026)
    pays = [x.contracts.payroll(t.id, 2026) for t in (x.mine, x.theirs)]
    assert set(budgets) == {x.mine.id, x.theirs.id}
    assert budgets[x.mine.id] == budgets[x.theirs.id] == bg.first_budget(pays)
    # Stored: asking again gives the same, even after payroll changes.
    x.factory.rated_player(x.theirs, x.league, level=80)
    x.contracts.sign_unsigned(x.league.id, 2026)
    assert x.budgets.for_league(x.league.id, 2026) == budgets


def test_next_seasons_budget_grows_from_this_ones(lg):
    x = lg()
    now = x.budgets.budget(x.league.id, x.mine.id, 2026)
    assert x.budgets.budget(x.league.id, x.mine.id, 2027) == bg.grown(now)


def test_speed_blitz_has_no_budgets(lg):
    x = lg(mode="speed_blitz")
    assert x.budgets.for_league(x.league.id, 2026) == {}
    assert x.budgets.standing(x.league.id, x.mine.id, 2026) is None


def test_the_tax_is_charged_on_payroll_over_budget(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    x.db.execute(
        "UPDATE team_budgets SET budget = 1000000 WHERE team_id = %s",
        (x.mine.id,),
    )
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
    x.db.execute(
        "UPDATE team_budgets SET budget = 900000000 WHERE team_id = %s",
        (x.mine.id,),
    )
    assert (
        free_agents.sign_preview(x.db, x.league.id, x.mine.id, pid)["warning"] is None
    )
    x.db.execute(
        "UPDATE team_budgets SET budget = 1000000 WHERE team_id = %s",
        (x.mine.id,),
    )
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


def test_the_roster_shows_payroll_against_budget(lg, client_for):
    x = lg()
    client = client_for(x)
    budget = x.budgets.budget(x.league.id, x.mine.id, 2026)
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert f"of {bg.format_salary(budget)}" in html
    x.db.execute(
        "UPDATE team_budgets SET budget = 1000000 WHERE team_id = %s",
        (x.mine.id,),
    )
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert "over · " in html and " tax</span>" in html


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
    assert budgets[x.mine.id] > budgets[x.theirs.id]
    average = (budgets[x.mine.id] + budgets[x.theirs.id]) / 2
    assert abs(average - bg.first_budget(pays)) <= 100_000
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
    # Next season's average budget still grows 5%.
    now = x.budgets.for_league(x.league.id, 2026)
    nxt = x.budgets.for_league(x.league.id, 2027)
    assert abs(sum(nxt.values()) / 2 - bg.grown(sum(now.values()) / 2)) <= 100_000
