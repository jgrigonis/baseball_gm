# tests/player/test_contracts.py
"""Contract pricing rules (src/player/contracts.py)."""

import random

from src.api.grade_curves import OVERALL_CUTOFFS
from src.player import contracts as ct


def test_rookie_deals_pay_early_picks_more_and_run_two_to_four_years():
    pays = [ct.rookie_salary(n) for n in (1, 5, 10, 30, 90)]
    assert pays == sorted(pays, reverse=True)
    assert pays[0] > 3_000_000
    assert pays[-1] == ct.MIN_SALARY
    deal = ct.rookie_deal(7)
    assert deal.years == ct.ROOKIE_YEARS == 3 and deal.kind == "rookie"
    lengths = [ct.rookie_years(f"p{i}") for i in range(300)]
    assert set(lengths) == {2, 3, 4}
    assert ct.rookie_years("p1") == ct.rookie_years("p1")
    assert ct.rookie_deal(7, years=4).years == 4


def test_arbitration_pays_a_growing_share_of_market_for_one_season():
    market = ct.Deal(10_000_000, 5, "standard")
    deals = [ct.arbitration_deal(market, s) for s in (3, 4, 5, 6)]
    assert [d.salary for d in deals] == [4_000_000, 5_500_000, 7_000_000, 8_500_000]
    assert all(d.years == 1 and d.kind == "arbitration" for d in deals)
    assert ct.arbitration_deal(market, 7) is None
    assert ct.arbitration_deal(market, 2) is None
    # Never below the minimum.
    cheap = ct.Deal(ct.MIN_SALARY, 1, "standard")
    assert ct.arbitration_deal(cheap, 3).salary == ct.MIN_SALARY


def test_grade_position_follows_the_curve():
    cuts = OVERALL_CUTOFFS["hitter"]
    assert ct.grade_position(cuts[0], "hitter") == 0  # bottom of A+
    assert ct.grade_position(cuts[4], "hitter") == 4  # bottom of B
    assert ct.grade_position(0, "hitter") == 12  # F
    assert ct.grade_position(cuts[0] + 3, "hitter") == -1


def test_better_players_are_paid_more_within_the_limits():
    pays = [ct.prime_salary(v, "hitter") for v in range(30, 100, 5)]
    assert pays == sorted(pays)
    assert ct.prime_salary(30, "hitter") == ct.MIN_SALARY
    assert ct.prime_salary(OVERALL_CUTOFFS["hitter"][0], "hitter") == 32_000_000
    assert ct.prime_salary(200, "hitter") == ct.MAX_SALARY


def test_old_players_sign_cheaper_shorter_deals():
    star = OVERALL_CUTOFFS["pitcher"][1]
    young = ct.standard_deal(27, star, "pitcher", random.Random(1))
    old = ct.standard_deal(37, star, "pitcher", random.Random(1))
    assert old.salary < young.salary
    assert old.years <= 2 < young.years


def test_fringe_players_go_year_to_year():
    for seed in range(20):
        deal = ct.standard_deal(25, 40, "hitter", random.Random(seed))
        assert deal.years <= 2 and deal.salary < 1_000_000


def test_salaries_are_rounded():
    for seed in range(50):
        s = ct.standard_deal(28, 66, "hitter", random.Random(seed)).salary
        assert s % (50_000 if s >= 1_000_000 else 10_000) == 0


def test_format_salary():
    assert ct.format_salary(780_000) == "$780K"
    assert ct.format_salary(4_500_000) == "$4.5M"
    assert ct.format_salary(32_000_000) == "$32M"
    assert ct.format_salary(None) == "—"


def test_a_scaled_deal_costs_more_and_moves_the_floor():
    import random as _r

    base = ct.standard_deal(27, 70, "hitter", _r.Random(1))
    grown = ct.standard_deal(27, 70, "hitter", _r.Random(1), 1.2)
    assert grown.years == base.years
    assert abs(grown.salary - base.salary * 1.2) <= 60_000
    assert ct.rookie_salary(200, 1.2) == ct.round_salary(ct.MIN_SALARY * 1.2, 1.2)
    assert ct.rookie_salary(200, 1.2) > ct.rookie_salary(200)
    assert ct.round_salary(1, 1.0) == ct.MIN_SALARY
