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


def _judge(roster, giving, getting, state="retooling", days_left=60):
    return evaluate(roster, giving, getting, state, days_left, 0.08)


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
    healthy = _judge(roster, [roster[0]], [_p(62)], state="contending")
    hurt = _judge(roster, [roster[0]], [_p(62, injured_days=70)], state="contending")
    assert healthy.accept
    assert not hurt.accept
    assert "hurt" in hurt.reason


def test_a_contender_wont_get_worse_this_season():
    roster = _roster()
    verdict = _judge(roster, [roster[0]], [_p(57, age=21)], state="contending")
    assert not verdict.accept
    assert "race" in verdict.reason


def test_a_seller_takes_youth_for_a_veteran():
    vet = _p(64, age=34)
    roster = _roster() + [vet]
    assert _judge(roster, [vet], [_p(62, age=22)], state="rebuilding").accept
    assert not _judge(roster, [vet], [_p(62, age=22)], state="contending").accept


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


def test_a_gm_who_trusts_stats_sees_form():
    hot = Asset(
        id="hot",
        name="Hot",
        is_pitcher=False,
        hit=60,
        sp=30,
        rp=30,
        age=27,
        form=(8.0, 0.0),
    )
    assert hot.seen(0.0) is hot
    assert hot.seen(1.0).hit == 68
    assert hot.seen(0.5).hit == 64
    assert hot.seen(0.5).id == "hot"
    arm = Asset(
        id="arm",
        name="Arm",
        is_pitcher=True,
        hit=20,
        sp=60,
        rp=50,
        age=27,
        form=(0.0, -6.0),
    )
    assert arm.seen(0.5).sp == 57
    assert arm.seen(0.5).rp < 50
    assert ai_evaluator.seen([hot, arm], 0.0) == [hot, arm]


def test_stats_can_tip_a_close_deal():
    roster = _roster()
    hot = Asset(
        id="hot2",
        name="Hot",
        is_pitcher=False,
        hit=58,
        sp=58,
        rp=58,
        age=27,
        form=(10.0, 0.0),
    )
    giving = [roster[0]]
    assert not _judge(roster, giving, [hot]).accept
    seen = ai_evaluator.seen
    assert evaluate(
        seen(roster, 1.0), seen(giving, 1.0), seen([hot], 1.0), "retooling", 60, 0.08
    ).accept


def test_margin_factor_scales_the_margin():
    base = margin("a", "b", "2026-05-01")
    assert margin("a", "b", "2026-05-01", 1.5) == base * 1.5
    assert margin("a", "b", "2026-05-01", 0.5) == base * 0.5


def test_horizon_tilts_now_against_later():
    assert ai_evaluator.weights("retooling") == ai_evaluator.STATE_WEIGHTS["retooling"]
    now, later = ai_evaluator.weights("retooling", 1.0)
    assert now > 0.55 and abs(now + later - 1) < 1e-9
    now, _ = ai_evaluator.weights("retooling", -1.0)
    assert now < 0.55
    # Never all one or the other.
    assert ai_evaluator.weights("all-in", 1.0)[1] > 0
