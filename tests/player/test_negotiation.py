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
