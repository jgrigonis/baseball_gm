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


def test_the_budget_tab_keeps_cap_spending_and_bank_apart(lg, client_for):
    """Payroll vs the cap, total spending vs the owner, and the bank are
    separate sections, and total spending shows what it adds up."""
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    html = client_for(x).get(f"/leagues/{x.league.id}/budget").text
    cap = x.budgets.cap(x.league.id, 2026)
    pay = bg.format_salary(x.contracts.payroll(x.mine.id, 2026))
    fo = bg.format_salary(bg.standard_front_office(cap))
    assert "Payroll and the league cap" in html
    assert "Spending and your owner" in html
    assert "Total spending" in html
    assert f"{pay} payroll + {fo} front office" in html
    spend_at = html.index("Spending and your owner")
    assert html.index("League cap") < spend_at < html.index("Owner's ideal budget")
    if "Owner's bank" in html:
        assert html.index("Owner's limit") < html.index("Owner's bank")


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


def test_coaching_helps_the_young_most():
    assert bg.coaching_growth(4, 21) == 1.15
    assert bg.coaching_growth(0, 21) == 0.85
    assert 1.0 < bg.coaching_growth(4, 25) < 1.15
    assert bg.coaching_growth(4, 30) == 1.0
    assert bg.coaching_growth(bg.STANDARD, 21) == 1.0


def test_facilities_move_injury_odds_and_days_out():
    assert bg.facilities_injury(4) < 1.0 < bg.facilities_injury(0)
    assert bg.facilities_injury(bg.STANDARD) == 1.0
    assert bg.facilities_days(4, 20) == 17 and bg.facilities_days(0, 20) == 23
    assert bg.facilities_days(4, 1) == 1 and bg.facilities_days(2, 9) == 9


def test_department_reads_levels_without_making_rows(lg):
    x = lg()
    assert x.budgets.department(x.league.id, 2026, "facilities", [x.mine.id]) == {
        x.mine.id: bg.STANDARD
    }
    x.budgets.for_league(x.league.id, 2026)
    x.budgets.set_level(x.league.id, x.mine.id, 2026, "facilities", 4)
    got = x.budgets.department(
        x.league.id, 2026, "facilities", [x.mine.id, x.theirs.id]
    )
    assert got[x.mine.id] == 4 and got[x.theirs.id] in range(5)


def test_analytics_levels_are_read_for_games(db_conn):
    """play_season reads Analytics the same way as Facilities."""
    from src.league.play_season import _department

    assert _department(db_conn, None, None, "analytics", ["a", "b"]) == {
        "a": bg.STANDARD,
        "b": bg.STANDARD,
    }


# ── The minor leagues count against spending (Josh, 2026-11-06) ─────────────


def _farm(x, team, n):
    """n never-guaranteed minor leaguers on the team, signed; their pay."""
    ids = [
        x.factory.rated_player(team, x.league, level=40, status="minors").id
        for _ in range(n)
    ]
    x.contracts.sign_unsigned(x.league.id, 2026)
    return ids, sum(c["salary"] for c in x.contracts.active_for(ids, 2026).values())


def test_owners_cover_a_farm_by_their_spending():
    assert bg.farm_share(0) == 0.8
    assert bg.farm_share(50) == 1.0
    assert bg.farm_share(100) == pytest.approx(1.2)
    assert bg.farm_allowance(50 * M, 5) == 41 * M
    assert bg.farm_allowance(50 * M, 95) == 59 * M
    assert bg.average_farm([2 * M, 3 * M]) == 2_500_000
    assert bg.average_farm([]) == 0


def test_the_farm_counts_full_salaries_against_spending_not_the_cap(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    before = x.budgets.standing(x.league.id, x.mine.id, 2026)
    assert before["minors"] == 0
    farm, pay = _farm(x, x.mine, 10)
    # And one who's been on the 40-man: he's payroll.
    vet = x.factory.rated_player(x.mine, x.league, level=40)
    x.contracts.sign_unsigned(x.league.id, 2026)
    x.contracts.guarantee([vet.id])
    x.db.execute(
        "UPDATE player_status SET status = 'minors' WHERE player_id = %s", (vet.id,)
    )
    assert pay >= 10 * ct.MIN_SALARY
    assert x.contracts.minor_league_pay([x.mine.id], 2026) == {x.mine.id: pay}

    after = x.budgets.standing(x.league.id, x.mine.id, 2026)
    assert after["minors"] == pay
    vet_pay = x.contracts.active(vet.id, 2026)["salary"]
    assert after["payroll"] == before["payroll"] + vet_pay
    assert after["tax"] == bg.luxury_tax(after["payroll"], after["cap"])
    assert after["spend"] == after["payroll"] + after["front_office"] + pay
    assert after["payroll_budget"] == (
        after["budget"] - after["front_office"] - after["minors"]
    )
    # Letting one go saves his salary.
    one = x.contracts.active(farm[0], 2026)["salary"]
    x.contracts.release(farm[0], x.mine.id, 2026)
    x.db.execute("DELETE FROM team_players WHERE player_id = %s", (farm[0],))
    assert x.budgets.standing(x.league.id, x.mine.id, 2026)["minors"] == pay - one


def test_budgets_grow_by_the_leagues_average_farm(lg):
    x = lg()
    stored = x.budgets.for_league(x.league.id, 2026)
    _, pay = _farm(x, x.mine, 20)
    budgets = x.budgets.for_league(x.league.id, 2026)
    # Mine has the whole farm, theirs none: each (middle) owner covers the
    # average, and it's worked out live, so the draft moves it.
    allowance = bg.average_farm([pay, 0])
    assert allowance > 0
    for t in (x.mine.id, x.theirs.id):
        assert budgets[t] == stored[t] + allowance
    s = x.budgets.standing(x.league.id, x.mine.id, 2026)
    assert s["farm_allowance"] == allowance


def test_a_miser_covers_less_of_the_farm(lg):
    x = lg()
    stored = x.budgets.for_league(x.league.id, 2026)
    _, pay = _farm(x, x.mine, 20)
    average = bg.average_farm([pay, 0])
    x.budgets._spending = lambda league_id: {x.mine.id: 5, x.theirs.id: 95}
    budgets = x.budgets.for_league(x.league.id, 2026)
    assert budgets[x.mine.id] == stored[x.mine.id] + bg.farm_allowance(average, 5)
    assert budgets[x.theirs.id] == stored[x.theirs.id] + bg.farm_allowance(average, 95)
    assert budgets[x.mine.id] - stored[x.mine.id] < average
    assert budgets[x.theirs.id] - stored[x.theirs.id] > average


def test_the_farm_comes_out_of_profit(lg):
    x = lg()
    _, pay = _farm(x, x.mine, 20)
    x.budgets.for_league(x.league.id, 2026)
    x.budgets.assess(x.league.id, 2026)
    rows = {
        r["team_id"]: r
        for r in x.db.execute(
            "SELECT team_id, minor_league FROM team_budgets"
            " WHERE league_id = %s AND year = 2026",
            (x.league.id,),
        ).fetchall()
    }
    assert rows[x.mine.id]["minor_league"] == pay
    assert rows[x.theirs.id]["minor_league"] == 0
    assert x.budgets.history(x.league.id, x.mine.id)[0]["minor_league"] == pay


def test_ai_budget_room_leaves_out_the_farm(lg):
    from src.api.services import ai_free_agents, owners

    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    room = ai_free_agents._budget_room(x.db, x.league.id, x.theirs.id, 2026)
    _, pay = _farm(x, x.theirs, 10)
    allowance = bg.average_farm([pay, 0])
    want = room - pay + allowance
    assert ai_free_agents._budget_room(x.db, x.league.id, x.theirs.id, 2026) == want
    rooms = owners.pay_rooms(x.db, x.league.id, x.season.id, [x.theirs.id])
    assert rooms[x.theirs.id] == want


def test_the_budget_tab_shows_the_minor_leagues(lg, client_for):
    x = lg()
    _, pay = _farm(x, x.mine, 10)
    x.budgets.for_league(x.league.id, 2026)
    html = client_for(x).get(f"/leagues/{x.league.id}/budget").text
    assert f"front office + {bg.format_salary(pay)} minor leagues" in html
    allowance = bg.format_salary(bg.average_farm([pay, 0]))
    assert f"includes {allowance} for the farm" in html


# ── Revenue breakdown ─────────────────────────────────────────────────────────


def test_books_add_up_and_back_out_the_revenue_base():
    from src.league import finances as fn

    b = fn.books(
        revenue=112 * M, market=4, fans=50, playoff_gate=4 * M,
        home_playoff_games=2, gate_per_game=2 * M, tax_share=3 * M,
        payroll=80 * M, front_office=10 * M, luxury_tax=0, costs=15 * M,
    )  # fmt: skip
    assert b["projected"] and b["base"] == 100 * M
    assert b["market_name"] == "Big"
    assert b["total_in"] == 119 * M and b["total_out"] == 105 * M
    assert b["profit"] == 14 * M and b["other"] == 0
    # A finished season's profit stands; anything left over is other costs.
    done = fn.books(
        revenue=112 * M, market=4, fans=50, playoff_gate=0,
        home_playoff_games=0, gate_per_game=2 * M, tax_share=0,
        payroll=80 * M, front_office=10 * M, luxury_tax=0, costs=15 * M,
        profit=5 * M,
    )  # fmt: skip
    assert not done["projected"] and done["other"] == 2 * M
    assert done["total_in"] - done["total_out"] == done["profit"]


def test_the_books_match_the_profit_the_season_closed_with(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    projected = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert [b["year"] for b in projected] == [2026] and projected[0]["projected"]
    x.budgets.assess(x.league.id, 2026)
    (closed,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert not closed["projected"]
    assert closed["other"] == 0
    assert closed["profit"] == projected[0]["profit"]
    x.budgets.for_league(x.league.id, 2027)
    books = x.budgets.books(x.league.id, x.mine.id, 2027)
    assert [(b["year"], b["projected"]) for b in books] == [(2027, True), (2026, False)]


def test_the_budget_tab_shows_the_revenue_breakdown(lg, client_for):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    html = client_for(x).get(f"/leagues/{x.league.id}/budget").text
    assert "Revenue and profit" in html and "Projected profit" in html
    assert "league base" in html and "Fixed costs" in html
    assert (
        "Spending" not in html.split("Revenue and profit")[1].split("Past seasons")[0]
    )


def test_speed_blitz_has_no_books(lg):
    x = lg(mode="speed_blitz")
    assert x.budgets.books(x.league.id, x.mine.id, 2026) == []


def test_the_books_count_the_farm_and_still_match_the_closed_profit(lg):
    x = lg()
    _, pay = _farm(x, x.mine, 10)
    x.budgets.for_league(x.league.id, 2026)
    (projected,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert projected["minor_league"] == pay
    assert projected["farm_help"] == bg.average_farm([pay, 0])
    x.budgets.assess(x.league.id, 2026)
    (closed,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert closed["other"] == 0 and closed["profit"] == projected["profit"]
    assert closed["minor_league"] == pay


# ── Ticket prices (Josh, 2026-11-07) ─────────────────────────────────────────


def test_ticket_prices_trade_revenue_now_for_fans_later():
    from src.league import finances as fn

    assert len(fn.TICKET_LEVELS) == 10 and fn.ticket_level(None) == 5
    assert fn.ticket_mult(5) == 1.0 and fn.ticket_fans(5) == 0
    mults = [fn.ticket_mult(level) for level in fn.TICKET_LEVELS]
    fans = [fn.ticket_fans(level) for level in fn.TICKET_LEVELS]
    assert mults == sorted(mults) and fans == sorted(fans, reverse=True)
    # Each step up earns no more than the one before it.
    steps = [b - a for a, b in zip(mults, mults[1:])]
    assert all(b <= a + 1e-9 for a, b in zip(steps, steps[1:]))
    assert fn.ticket_level(0) == 1 and fn.ticket_level(99) == 10
    base = fn.fans_after(50, 0.5, False, False, 0)
    assert fn.fans_after(50, 0.5, False, False, 0, 10) < base
    assert fn.fans_after(50, 0.5, False, False, 0, 1) > base


def test_ticket_prices_change_profit_fans_and_the_books(lg):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    assert x.budgets.ticket_price(x.league.id, x.mine.id, 2026) == 5
    (normal,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert normal["tickets"] == 0
    x.budgets.set_ticket_price(x.league.id, x.mine.id, 2026, 9)
    assert x.budgets.ticket_price(x.league.id, x.mine.id, 2026) == 9
    (high,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert high["tickets"] > 0
    assert high["profit"] == normal["profit"] + high["tickets"]
    x.budgets.assess(x.league.id, 2026)
    (closed,) = x.budgets.books(x.league.id, x.mine.id, 2026)
    assert closed["other"] == 0 and closed["profit"] == high["profit"]
    rows = {
        r["team_id"]: r["fans_after"]
        for r in x.db.execute(
            "SELECT team_id, fans_after FROM team_budgets WHERE league_id = %s",
            (x.league.id,),
        ).fetchall()
    }
    # Same record (no games), but pricier tickets cooled my fans.
    assert rows[x.mine.id] < rows[x.theirs.id]


def test_ticket_prices_are_set_between_seasons_on_the_budget_tab(lg, client_for):
    x = lg()
    x.budgets.for_league(x.league.id, 2026)
    client = client_for(x)
    html = client.get(f"/leagues/{x.league.id}/budget").text
    assert "Ticket prices" in html and 'type="range"' in html
    url = f"/leagues/{x.league.id}/budget/tickets"
    html = client.post(url, data={"level": 8}).text
    assert "between seasons" in html
    assert x.budgets.ticket_price(x.league.id, x.mine.id, 2026) == 5
    x.db.execute("UPDATE leagues SET state = 'preseason' WHERE id = %s", (x.league.id,))
    client.post(url, data={"level": 8})
    assert x.budgets.ticket_price(x.league.id, x.mine.id, 2026) == 8
    html = client.get(f"/leagues/{x.league.id}/budget").text
    assert "Premium (8 of 10)" in html
