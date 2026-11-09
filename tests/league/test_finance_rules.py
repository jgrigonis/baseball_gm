# tests/league/test_finance_rules.py
"""Fan interest, revenue and owner-set budgets (src/league/finances.py)."""

from src.league import finances as fn

M = 1_000_000


def test_spenders_get_a_bigger_share_than_misers():
    assert fn.spend_share(0) == fn.SHARE_LOW
    assert fn.spend_share(100) == fn.SHARE_LOW + fn.SHARE_SPAN
    assert fn.spend_share(5) < fn.spend_share(50) < fn.spend_share(95)


def test_budgets_come_from_the_cap_by_spending():
    teams = {
        "big_spender": fn.TeamMoney(market=5, fans=70, spending=95),
        "small_miser": fn.TeamMoney(market=1, fans=40, spending=5),
        "middle": fn.TeamMoney(market=3, fans=50, spending=50),
    }
    plans = fn.plan(160 * M, teams)
    # Budgets pay a Standard front office on top of payroll.
    fo = fn.bg.standard_front_office(160 * M)
    assert plans["small_miser"].budget - fo < 160 * M < plans["big_spender"].budget - fo
    assert (
        plans["big_spender"].budget
        > plans["middle"].budget
        > plans["small_miser"].budget
    )
    # A big market brings in more.
    assert plans["big_spender"].revenue > plans["small_miser"].revenue


def test_same_market_and_fans_different_owner_same_revenue():
    plans = fn.plan(
        150 * M,
        {
            "a": fn.TeamMoney(market=3, fans=50, spending=10),
            "b": fn.TeamMoney(market=3, fans=50, spending=90),
        },
    )
    assert plans["a"].revenue == plans["b"].revenue
    assert plans["a"].budget < plans["b"].budget


def test_fans_follow_winning():
    # An average team without October drifts down a little; the bonuses
    # make it up for teams that earn them.
    assert fn.fans_after(50, 0.5, False, False, 0) == 50 - round(
        fn.FAN_STEP * fn.FAN_DRIFT
    )
    assert fn.fans_after(50, 0.62, True, False, 2) > 58
    assert fn.fans_after(50, 0.38, False, False, 0) < 42
    title = fn.fans_after(50, 0.6, True, True, 3)
    assert title > fn.fans_after(50, 0.6, True, False, 3)
    # Moves part of the way, and stays in range.
    assert fn.fans_after(90, 0.75, True, True, 8) <= fn.FAN_MAX
    assert fn.fans_after(10, 0.25, False, False, 0) >= fn.FAN_MIN


def test_profit_takes_off_payroll_tax_and_costs():
    assert fn.profit(250 * M, 160 * M, 5 * M, 50 * M) == 35 * M
    assert fn.playoff_gate(250 * M, 0) == 0
    assert fn.playoff_gate(250 * M, 4) == 360 * M


def test_only_keen_fans_bring_in_popularity_money():
    assert fn.popularity_money(250 * M, 40) == 0
    assert fn.popularity_money(250 * M, fn.POPULARITY_FROM) == 0
    # Half way from 55 to 100: half of 15% of average revenue.
    assert fn.popularity_money(250 * M, 77.5) == 18_800_000
    assert fn.popularity_money(250 * M, 100) == 37_500_000


def test_the_books_count_popularity_money_in():
    kw = dict(
        revenue=200 * M, market=3, fans=80, playoff_gate=0, home_playoff_games=0,
        gate_per_game=7 * M, tax_share=0, payroll=150 * M, front_office=20 * M,
        luxury_tax=0, costs=10 * M,
    )  # fmt: skip
    plain = fn.books(**kw)
    popular = fn.books(**kw, popularity=20 * M)
    assert popular["total_in"] == plain["total_in"] + 20 * M
    assert popular["profit"] == plain["profit"] + 20 * M


# ── Broadcast deals and merchandise (Josh, 2026-11-09) ────────────────────────


def test_jerseys_sell_by_grade_with_star_and_new_team_bumps():
    cap = fn.MERCH_CAP
    assert fn.jersey_money("B", cap) == 0
    assert fn.jersey_money("B+", cap) == 1 * M
    assert fn.jersey_money("A+", cap) == 10 * M
    assert fn.jersey_money("A", cap, all_star=True) == 9 * M
    assert fn.jersey_money("A", cap, award=True, new=True) == 18 * M
    # Prices grow with the cap.
    assert fn.jersey_money("A", cap * 2) == 12 * M


def test_merchandise_follows_market_fans_marketing_and_games():
    star = fn.Seller("p1", "A", share=1.0)
    half = fn.Seller("p2", "A+", share=0.5)
    nobody = fn.Seller("p3", "C", share=1.0)
    total, parts = fn.merchandise([star, half, nobody], fn.MERCH_CAP, 3, 50)
    # Market 3 and fans 50 are x1; the A+ played half his games here.
    assert total == 11 * M
    assert [s.player_id for s, _ in parts] == ["p1", "p2"]
    big, _ = fn.merchandise([star], fn.MERCH_CAP, 5, 100, marketing=4)
    small, _ = fn.merchandise([star], fn.MERCH_CAP, 1, 0, marketing=0)
    assert big > 2 * small > 0


def test_broadcast_deals_pay_popular_winners_in_big_markets():
    avg = 265 * M
    worst = fn.broadcast_base(avg, 1, 0, 0.30)
    middle = fn.broadcast_base(avg, 3, 50, 0.50)
    best = fn.broadcast_base(avg, 5, 100, 0.70)
    assert worst == round(avg * 0.06 * 0.8 / 100_000) * 100_000
    assert worst < middle < best
    assert 12 * M < worst < 15 * M and 50 * M < best < 55 * M
    assert fn.broadcast_amount(middle, 5) > fn.broadcast_amount(middle, 3)
    assert fn.broadcast_amount(middle, 2) == middle
    assert fn.broadcast_years(4) == fn.BROADCAST_DEFAULT_YEARS


def test_the_books_count_broadcast_and_merchandise_in():
    kw = dict(
        revenue=250 * M, market=3, fans=50, playoff_gate=0, home_playoff_games=0,
        gate_per_game=9 * M, tax_share=0, payroll=150 * M, front_office=20 * M,
        luxury_tax=0, costs=80 * M,
    )  # fmt: skip
    plain = fn.books(**kw)
    more = fn.books(**kw, broadcast=30 * M, merchandise=12 * M)
    assert more["total_in"] == plain["total_in"] + 42 * M
    assert more["profit"] == plain["profit"] + 42 * M


def test_hall_of_famers_sell_retro_jerseys_most_after_induction():
    cap = fn.MERCH_CAP
    assert fn.jersey_money(fn.HALL_GRADE, cap) == fn.HALL_JERSEY
    assert fn.jersey_money(fn.HALL_GRADE, cap, new=True) == 3 * fn.HALL_JERSEY
    legend = fn.Seller("old", fn.HALL_GRADE, share=1.0)
    assert legend.hall
    total, _ = fn.merchandise([legend], cap, 3, 50)
    assert total == 1_500_000
