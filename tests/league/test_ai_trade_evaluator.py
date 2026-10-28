# tests/league/test_ai_trade_evaluator.py
"""How an AI GM judges an offer (src/league/trades/ai_evaluator.py)."""

from itertools import count

from src.league.trades import ai_evaluator
from src.league.trades.ai_evaluator import Asset, evaluate, margin

_ids = count()


def _p(rating, pitcher=False, age=27, injured_days=0):
    return Asset(
        id=f"p{next(_ids)}",
        name=f"Player {rating}",
        is_pitcher=pitcher,
        hit=rating,
        sp=rating,
        rp=rating,
        age=age,
        injured_days=injured_days,
    )


def _roster(level=58):
    return [_p(level) for _ in range(13)] + [_p(level, pitcher=True) for _ in range(13)]


def _judge(roster, giving, getting, stance="neutral", days_left=60):
    return evaluate(roster, giving, getting, stance, days_left, 0.08)


def test_trading_up_is_accepted():
    roster = _roster()
    mine = _p(66)
    assert _judge(roster, [roster[0]], [mine]).accept


def test_an_even_swap_is_turned_down():
    roster = _roster()
    assert not _judge(roster, [roster[0]], [_p(58)]).accept


def test_quantity_doesnt_buy_quality():
    star = _p(74)
    roster = _roster() + [star]
    verdict = _judge(roster, [star], [_p(62), _p(62), _p(62)])
    assert not verdict.accept


def test_a_fourth_good_bench_bat_is_worth_little():
    # A deep team gives up a starter for a bench-level upgrade.
    roster = _roster(60) + [_p(60) for _ in range(6)]
    assert not _judge(roster, [roster[0]], [_p(57), _p(57)]).accept


def test_an_injured_player_is_worth_less_now():
    # Out for the rest of the season: a contender won't take him.
    roster = _roster()
    healthy = _judge(roster, [roster[0]], [_p(62)], stance="contender")
    hurt = _judge(roster, [roster[0]], [_p(62, injured_days=70)], stance="contender")
    assert healthy.accept
    assert not hurt.accept
    assert "hurt" in hurt.reason


def test_a_contender_wont_get_worse_this_season():
    roster = _roster()
    verdict = _judge(roster, [roster[0]], [_p(57, age=21)], stance="contender")
    assert not verdict.accept
    assert "race" in verdict.reason


def test_a_seller_takes_youth_for_a_veteran():
    vet = _p(64, age=34)
    roster = _roster() + [vet]
    assert _judge(roster, [vet], [_p(62, age=22)], stance="seller").accept
    assert not _judge(roster, [vet], [_p(62, age=22)], stance="contender").accept


def test_the_margin_is_the_same_all_day_and_moves_between_days():
    assert margin("a", "b", "2025-07-01") == margin("a", "b", "2025-07-01")
    days = {margin("a", "b", f"2025-07-{d:02d}") for d in range(1, 20)}
    assert len(days) > 1
    lo = ai_evaluator.BASE_MARGIN - ai_evaluator.MARGIN_NOISE
    hi = ai_evaluator.BASE_MARGIN + ai_evaluator.MARGIN_NOISE
    assert all(lo <= m <= hi for m in days)


def test_value_is_zero_at_replacement_and_grows_faster_than_the_rating():
    r = ai_evaluator.REPLACEMENT
    assert ai_evaluator.value(r - 5) == 0
    assert ai_evaluator.value(r + 20) > 2 * ai_evaluator.value(r + 10)
