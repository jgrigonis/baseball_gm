# tests/player/test_negotiation.py
"""A free agent's answer to an offer (src/player/negotiation.py)."""

import pytest

from src.api.services.fa_offers import round_up
from src.player import negotiation as ng

ASK = 10_000_000


def _s(**kw):
    base = dict(
        ask_salary=ASK,
        ask_years=3,
        age=27,
        fit=0.0,
        share=0.5,
        ego=50,
        temper=50,
        loyalty=50,
        minimum=780_000,
    )
    base.update(kw)
    return ng.Stance(**base)


def test_each_season_counts_by_his_age_in_it():
    # A 27-year-old's 5-year deal covers his age 30 and 31 seasons.
    assert ng.season_value(27, 5) - ng.season_value(27, 3) == pytest.approx(
        2 * ng.SENIOR_SEASON
    )
    assert ng.season_value(24, 5) - ng.season_value(24, 3) == pytest.approx(
        2 * ng.YOUNG_SEASON
    )


def test_a_27_year_old_gives_a_discount_for_a_5_year_deal():
    s = _s()
    assert not s.takes(9_300_000, 3)
    assert s.takes(9_300_000, 5)
    assert s.counter(5, round_up) < s.counter(3, round_up)


def test_his_asking_deal_is_always_a_yes():
    s = _s(ego=100, star=True, callers=3, fit=-1.0, share=1.0)
    assert s.takes(ASK, 3)


def test_never_under_the_minimum():
    s = _s(ask_salary=800_000, minimum=780_000, fit=1.0, share=1.0, ego=0)
    assert not s.takes(700_000, 3)
    assert s.counter(3, round_up) >= 780_000


def test_the_floor_is_80_percent_unless_everything_favors_the_club():
    assert _s().floor == 8_000_000
    # A new club can't get all the way down: loyalty only helps his old one.
    assert _s(fit=1.0, share=1.0, ego=0).floor > 7_000_000
    best = _s(fit=1.0, share=1.0, ego=0, old_club=True, loyalty=100)
    assert best.floor == 7_000_000


def test_what_raises_his_bar():
    base = _s().bar
    assert _s(ego=90).bar > base
    assert _s(star=True).bar > base
    assert _s(callers=2).bar > _s(callers=1).bar > base
    assert _s(released_by=True).bar > base
    assert _s(old_club=True, loyalty=80).bar < base


def test_a_good_fit_takes_less():
    assert _s(fit=0.8, share=0.9).counter(3, round_up) < _s().counter(3, round_up)


def test_a_lowball_insults_a_hot_tempered_player_only():
    hot = _s(temper=100)
    want = hot.counter(3, round_up)
    assert hot.insulted(int(want * 0.5), want, "x")
    assert not hot.insulted(int(want * 0.95), want, "x")
    assert not _s(temper=100, easygoing=True).insulted(int(want * 0.5), want, "x")
    assert not _s(temper=40).insulted(int(want * 0.5), want, "x")


def test_the_counter_is_a_yes():
    for kw in ({}, {"ego": 90, "callers": 3}, {"fit": 0.9, "share": 0.9}):
        s = _s(**kw)
        for years in (1, 3, 6):
            c = s.counter(years, round_up)
            assert s.takes(c, years)


def test_hints_never_show_numbers():
    lines = ng.hints(_s(callers=2, fit=0.9, share=0.9, released_by=True))
    assert "Has other teams calling." in lines
    assert not any(ch.isdigit() for line in lines for ch in line)


# ── Money and re-signing at home (Josh, 2026-11-18) ──────────────────────────


def test_a_money_driven_player_has_a_higher_bar_and_floor():
    assert _s(money=100).bar == pytest.approx(_s().bar + ng.MONEY_PULL)
    assert _s(money=100).floor > _s().floor
    # Under MONEY_START it changes nothing.
    assert _s(money=40).bar == _s(money=0).bar


def test_at_home_loyalty_counts_more_the_longer_he_has_been_there():
    new = _s(home=True, loyalty=80, seasons=0)
    old = _s(home=True, loyalty=80, seasons=6)
    assert old.bar < new.bar < _s().bar
    assert _s(home=True).floor == 8_500_000


def test_a_grudge_follows_temper_money_and_loyalty():
    s = _s(home=True, temper=80, loyalty=20, money=80)
    assert s.grudge(9_500_000, 10_000_000) == 0  # a fair try
    g = s.grudge(8_000_000, 10_000_000)
    assert g > 0
    assert s.grudge(8_000_000, 10_000_000, insulted=True) == pytest.approx(2 * g)
    assert (
        _s(home=True, temper=80, loyalty=90, money=80).grudge(8_000_000, 10_000_000) < g
    )
    assert _s(home=True, easygoing=True).grudge(5_000_000, 10_000_000) == 0


def test_refusing_after_an_insult_is_mostly_for_the_hot_and_the_disloyal():
    calm = _s(temper=50, loyalty=50).refuse_chance()
    hot = _s(temper=90, loyalty=50).refuse_chance()
    cold = _s(temper=50, loyalty=10).refuse_chance()
    both = _s(temper=90, loyalty=10).refuse_chance()
    assert calm == pytest.approx(ng.REFUSE_BASE)
    assert hot == pytest.approx(cold) and 0.3 < hot < 0.35
    assert both == ng.REFUSE_MAX
    assert _s(temper=100, loyalty=0, easygoing=True).refuse_chance() == ng.REFUSE_BASE


def test_home_insults_need_a_big_lowball_and_never_bother_the_easygoing():
    s = _s(home=True, temper=50)
    assert not s.home_insulted(8_000_000, 10_000_000, 0.0)
    assert s.home_insulted(7_000_000, 10_000_000, 0.0)
    assert not _s(home=True, easygoing=True).home_insulted(1_000_000, 10_000_000, 0.0)
    # Hotter tempers take it personally more often.
    assert _s(home=True, temper=100).home_insulted(7_000_000, 10_000_000, 0.95)
    assert not _s(home=True, temper=30).home_insulted(7_000_000, 10_000_000, 0.6)


def test_a_veteran_asking_the_minimum_for_two_seasons_can_be_offered_one():
    # Josh, 2026-11-18: a 39-year-old asking the minimum for 2 seasons.
    low = 950_000
    vet = dict(ask_salary=low, ask_years=2, age=39, minimum=low, home=True)
    # A loyal one with years at his club takes a single season at the minimum.
    assert _s(**vet, loyalty=70, seasons=6).takes(low, 1)
    # A proud one wants a little more for giving up the second season, never
    # a lowball he'd hold against you or be insulted by.
    proud = _s(**vet, ego=90, loyalty=20, seasons=1)
    assert not proud.takes(low, 1)
    want = proud.counter(1, round_up)
    assert low < want <= low * ng.MAX_COUNTER
    assert proud.grudge(low, want) == 0
    assert not proud.home_insulted(low, want, 0.0)
