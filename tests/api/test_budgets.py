# tests/api/test_budgets.py
"""The league's payroll cap, owners' budgets and the luxury tax
(src/league/budget.py, src/db/repositories/budget_repo.py), and the
warnings."""

import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import free_agents
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.league import budget as bg
from src.player import contracts as ct
from src.player.player_value import role_rating

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
    fo = bg.standard_front_office(cap)
    assert budgets[x.mine.id] == budgets[x.theirs.id] == bg.owner_budget(cap, 50) + fo
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
    # Over the cap and the budget, but inside the owner's hard limit.
    pay = x.contracts.payroll(x.mine.id, 2026)
    x.db.execute("UPDATE team_budgets SET budget = %s, cap = %s", (pay + 100 * M, pay))
    preview = free_agents.sign_preview(x.db, x.league.id, x.mine.id, pid)
    assert "luxury tax" in preview["warning"] and preview["blocked"] is None
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
    assert f"Cap {bg.format_salary(cap)}" in html
    fo = bg.standard_front_office(cap)
    assert f"Owner's number {bg.format_salary(budget - fo)}" in html
    x.db.execute("UPDATE team_budgets SET budget = 1000000, cap = 1000000")
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert " over cap</span>" in html and "past it." in html
    x.db.execute("UPDATE team_budgets SET cap = 900000000")
    html = client.get(f"/leagues/{x.league.id}/roster").text
    assert " past owner</span>" in html


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
    fo = bg.standard_front_office(cap)
    assert budgets[x.mine.id] - fo == bg.owner_budget(cap, 95) > cap
    assert budgets[x.theirs.id] - fo == bg.owner_budget(cap, 5) < cap
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


# ── Prices follow the cap, the tax is shared (plans/budget.md Q2, Q6) ─────────


def test_prices_grow_in_step_with_the_cap():
    assert bg.salary_scale(0) == 1.0
    assert bg.salary_scale(-2) == 1.0
    assert bg.salary_scale(2) == pytest.approx(1.1025)


def test_the_tax_is_split_among_teams_under_the_cap():
    pays = {"rich": 180 * M, "mid": 165 * M, "cheap": 150 * M, "frugal": 140 * M}
    # Tax: 10M + 2.5M = 12.5M, split between the two under the cap.
    assert bg.tax_shares(pays, 160 * M) == {"cheap": 6_200_000, "frugal": 6_200_000}
    assert bg.tax_shares({"a": 150 * M}, 160 * M) == {}
    assert bg.tax_shares({"a": 170 * M}, 160 * M) == {}


def test_salary_scale_counts_from_the_leagues_first_cap(lg):
    x = lg()
    assert x.budgets.salary_scale(x.league.id, 2026) == 1.0  # no cap yet
    x.budgets.for_league(x.league.id, 2026)
    assert x.budgets.salary_scale(x.league.id, 2026) == 1.0
    assert x.budgets.salary_scale(x.league.id, 2028) == pytest.approx(1.1025)
    blitz = lg(mode="speed_blitz")
    assert blitz.budgets.salary_scale(blitz.league.id, 2030) == 1.0


def test_new_deals_later_in_a_league_cost_more(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    pid = x.factory.rated_player(x.mine, x.league, level=75).id
    x.contracts.sign_unsigned(x.league.id, 2029)
    record = PlayerRepository(x.db).look_up(pid)
    kind = "pitcher" if record.is_pitcher() else "hitter"
    flat = ct.standard_deal(
        record.age, role_rating(record), kind, random.Random(f"contract:{pid}:2029")
    )
    later = x.contracts.active(pid, 2029)["salary"]
    assert abs(later - flat.salary * 1.05**3) <= 60_000


def test_teams_under_the_cap_get_a_share_of_the_tax(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    mine = x.contracts.payroll(x.mine.id, 2026)
    theirs = x.contracts.payroll(x.theirs.id, 2026)
    assert mine > theirs
    cap = (mine + theirs) // 2
    x.db.execute("UPDATE team_budgets SET cap = %s", (cap,))
    taxes = x.budgets.assess(x.league.id, 2026)
    money = x.budgets.finances(x.league.id, 2026)
    assert taxes[x.mine.id] > 0 and money[x.mine.id]["tax_share"] == 0
    share = money[x.theirs.id]["tax_share"]
    assert abs(share - taxes[x.mine.id]) <= bg.CAP_ROUNDING // 2


# ── The owner's bank and hard limit (plans/budget.md, Q4 and Q5) ──────────────


def test_rich_owners_start_with_a_bank_by_spending():
    assert bg.starting_bank(160 * M, 5) == 88 * M
    assert bg.starting_bank(160 * M, 95) == 232 * M


def test_the_bank_moves_the_budget_a_little():
    assert bg.bank_adjust(160 * M, 0) == 0
    assert bg.bank_adjust(160 * M, 30 * M) == 6 * M
    assert bg.bank_adjust(160 * M, -500 * M) == -16 * M  # at most 10% of the cap
    assert bg.owner_budget(160 * M, 35, 30 * M) == 166 * M


def test_the_hard_limit_and_refusal():
    assert bg.hard_limit(160 * M, 170 * M, 50 * M) == 186 * M
    assert bg.hard_limit(160 * M, 170 * M, 0) == 170 * M  # bank's dry
    assert bg.refusal(180 * M, 186 * M, 5 * M) is None
    assert bg.refusal(180 * M, 186 * M, -5 * M) is None
    assert "$186M limit" in bg.refusal(180 * M, 186 * M, 10 * M)


def _owned(x, spending=50):
    x.db.execute(
        """INSERT INTO owner_personas (id, name, archetype, bio, weights, traits)
           VALUES ('own1', 'Rich Cat', 'The Tycoon', '', '{}', %s)
           ON CONFLICT (id) DO NOTHING""",
        (f'{{"spending": {spending}}}',),
    )
    x.db.execute(
        """INSERT INTO team_owners (league_id, team_id, owner_id, since_year)
           VALUES (%s, %s, 'own1', 2026)""",
        (x.league.id, x.mine.id),
    )


def test_the_bank_carries_profit_into_next_seasons_budget(lg):
    x = lg()
    _owned(x, spending=95)
    x.budgets.for_league(x.league.id, 2026)
    cap = x.budgets.cap(x.league.id, 2026)
    bank = x.budgets.banks(x.league.id)[x.mine.id]
    assert bank["start"] == bg.starting_bank(cap, 95) == bank["balance"]
    x.budgets.assess(x.league.id, 2026)
    profit = x.budgets.finances(x.league.id, 2026)[x.mine.id]["profit"]
    assert x.budgets.banks(x.league.id)[x.mine.id]["balance"] == bank["start"] + profit
    # Assessing again doesn't count the season twice.
    x.budgets.assess(x.league.id, 2026)
    assert x.budgets.banks(x.league.id)[x.mine.id]["change"] == profit
    nxt = x.budgets.for_league(x.league.id, 2027)[x.mine.id]
    cap2 = x.budgets.cap(x.league.id, 2027)
    assert nxt == bg.owner_budget(cap2, 95, profit) + bg.standard_front_office(cap2)
    history = x.budgets.history(x.league.id, x.mine.id)
    assert [r["year"] for r in history] == [2027, 2026]
    assert history[1]["bank_after"] == bank["start"] + profit


def test_the_owner_refuses_a_signing_past_the_limit(lg):
    x = lg()
    pid = x.factory.rated_player(x.theirs, x.league, level=70, status="free_agent").id
    x.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    x.budgets.for_league(x.league.id, 2026)
    pay = x.contracts.payroll(x.mine.id, 2026)
    x.db.execute("UPDATE team_budgets SET budget = %s, cap = %s", (pay, M))
    preview = free_agents.sign_preview(x.db, x.league.id, x.mine.id, pid)
    assert "won't allow" in preview["blocked"]
    with pytest.raises(free_agents.FreeAgentError, match="won't allow"):
        free_agents.sign(x.db, x.league.id, x.mine.id, pid)


def test_the_budget_tab(lg, client_for):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    x.budgets.assess(x.league.id, 2026)
    r = client_for(x).get(f"/leagues/{x.league.id}/budget")
    assert r.status_code == 200
    assert "Owner's limit" in r.text and "Past seasons" in r.text
    assert "2026" in r.text


def test_speed_blitz_has_no_budget_tab(lg, client_for):
    x = lg(mode="speed_blitz")
    r = client_for(x).get(f"/leagues/{x.league.id}/roster")
    assert f"/leagues/{x.league.id}/budget" not in r.text
    x = lg()
    r = client_for(x).get(f"/leagues/{x.league.id}/roster")
    assert f"/leagues/{x.league.id}/budget" in r.text


def test_the_owner_refuses_a_trade_that_adds_payroll_past_the_limit(lg):
    from src.api.services import trades

    x = lg()
    star = x.factory.rated_player(x.theirs, x.league, level=80).id
    x.contracts.sign_unsigned(x.league.id, 2026)
    x.contracts.guarantee([star])
    x.budgets.for_league(x.league.id, 2026)
    pay = x.contracts.payroll(x.mine.id, 2026)
    x.db.execute("UPDATE team_budgets SET budget = %s, cap = %s", (pay, M))
    assert "won't allow" in trades.owner_refusal(
        x.db, x.league.id, x.mine.id, [star], []
    )
    # Sending him away is always fine.
    assert trades.owner_refusal(x.db, x.league.id, x.theirs.id, [], [star]) is None


# ── The front office (plans/budget.md, section 7) ─────────────────────────────


def test_department_levels_cost_a_share_of_the_cap():
    assert [bg.level_cost(160 * M, i) for i in range(5)] == [
        2 * M,
        4 * M,
        6 * M,
        9 * M,
        12 * M,
    ]
    assert bg.standard_front_office(160 * M) == 18 * M
    assert bg.front_office_cost(160 * M, {"coaching": 4}) == 24 * M
    assert bg.clean_level("x") == bg.STANDARD and bg.clean_level(9) == 4


def test_ai_levels_follow_the_owners_spending():
    miser = bg.ai_levels(5, "a")
    spender = bg.ai_levels(95, "a")
    assert set(miser) == set(bg.DEPARTMENT_KEYS)
    assert sum(spender.values()) > sum(miser.values())


def test_the_front_office_counts_against_the_budget_not_the_cap(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    before = x.budgets.standing(x.league.id, x.mine.id, 2026)
    assert x.budgets.levels(x.league.id, x.mine.id, 2026) == dict.fromkeys(
        bg.DEPARTMENT_KEYS, bg.STANDARD
    )
    x.budgets.set_level(x.league.id, x.mine.id, 2026, "coaching", 4)
    after = x.budgets.standing(x.league.id, x.mine.id, 2026)
    cap = after["cap"]
    extra = bg.level_cost(cap, 4) - bg.level_cost(cap, bg.STANDARD)
    assert after["front_office"] == before["front_office"] + extra
    assert after["spend"] == after["payroll"] + after["front_office"]
    assert after["tax"] == before["tax"]  # tax is payroll only
    # It's in the season's profit.
    x.budgets.assess(x.league.id, 2026)
    money = x.budgets.finances(x.league.id, 2026)
    row = x.db.execute(
        "SELECT front_office FROM team_budgets WHERE team_id = %s AND year = 2026",
        (x.mine.id,),
    ).fetchone()
    assert row["front_office"] == after["front_office"]
    assert money[x.mine.id]["profit"] is not None


def test_ai_teams_get_their_own_levels(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    row = x.db.execute(
        "SELECT coaching FROM team_budgets WHERE team_id = %s", (x.theirs.id,)
    ).fetchone()
    assert row["coaching"] is not None
    mine = x.db.execute(
        "SELECT coaching FROM team_budgets WHERE team_id = %s", (x.mine.id,)
    ).fetchone()
    assert mine["coaching"] is None  # a person's starts at Standard


def test_setting_the_front_office_on_the_budget_tab(lg, client_for):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    client = client_for(x)
    url = f"/leagues/{x.league.id}/budget/front-office"
    # Locked during the season.
    r = client.post(url, data={"department": "coaching", "level": 4})
    assert "between seasons" in r.text
    assert x.budgets.levels(x.league.id, x.mine.id, 2026)["coaching"] == bg.STANDARD
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    x.db.execute("UPDATE team_budgets SET budget = 900000000")
    r = client.post(url, data={"department": "coaching", "level": 4})
    assert r.status_code == 200 and "Front office saved" in r.text
    assert x.budgets.levels(x.league.id, x.mine.id, 2026)["coaching"] == 4
    # The owner won't fund a raise past their hard limit.
    x.db.execute("UPDATE team_budgets SET budget = 1000000, cap = 1000000")
    r = client.post(url, data={"department": "analytics", "level": 4})
    assert "won't allow" in r.text
    assert x.budgets.levels(x.league.id, x.mine.id, 2026)["analytics"] == bg.STANDARD
    # Cutting back is always fine.
    r = client.post(url, data={"department": "coaching", "level": 0})
    assert x.budgets.levels(x.league.id, x.mine.id, 2026)["coaching"] == 0
