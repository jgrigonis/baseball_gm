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
    assert fn.playoff_gate(250 * M, 4) == 12 * M
