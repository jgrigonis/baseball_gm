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


def test_a_seller_wants_younger_players_back_for_a_young_star():
    young_star = _p(66, age=24)
    roster = _roster() + [young_star]
    verdict = _judge(roster, [young_star], [_p(62, age=31)], state="rebuilding")
    assert not verdict.accept
    assert "younger talent" in verdict.reason


def test_a_seller_offered_a_weak_young_player_says_he_isnt_enough():
    # An 18-year-old who doesn't make up for the player going isn't turned
    # down for being too old.
    vet = _p(64, age=26)
    roster = _roster() + [vet]
    kid = _p(48, age=18)
    verdict = _judge(roster, [vet], [kid], state="rebuilding")
    assert not verdict.accept
    assert "younger" not in verdict.reason
    assert kid.name in verdict.reason and vet.name in verdict.reason


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


def test_a_team_asks_less_for_a_player_who_wants_out():
    from dataclasses import replace

    roster = _roster()
    content = roster[0]
    unhappy = replace(content, wants_out=True)
    a = _judge(roster, [content], [_p(58)])
    b = _judge([unhappy, *roster[1:]], [unhappy], [_p(58)])
    assert b.threshold < a.threshold


def test_a_team_pays_less_for_a_player_who_wants_out():
    from dataclasses import replace

    roster = _roster()
    star = _p(70)
    a = _judge(roster, [roster[0]], [star])
    b = _judge(roster, [roster[0]], [replace(star, wants_out=True)])
    assert b.score < a.score


def test_an_ai_team_wont_take_on_more_salary_than_its_owner_allows():
    from src.league.trades import ai_evaluator as ev

    def p(pid, hit, salary):
        return ev.Asset(pid, pid, False, hit, 0, 0, 28, salary=salary)

    roster = [p(f"r{i}", 50, 1_000_000) for i in range(20)]
    star = p("star", 80, 30_000_000)
    scrub = roster[0]
    yes = ev.evaluate(roster, [scrub], [star], "contending", 100, 0.1)
    assert yes.accept
    no = ev.evaluate(
        roster, [scrub], [star], "contending", 100, 0.1, pay_room=5_000_000
    )
    assert not no.accept and no.reason == ev.OVER_BUDGET_REASON
    # Shedding salary is always fine.
    shed = ev.evaluate(
        roster + [star], [star], [scrub], "rebuilding", 100, 0.0, pay_room=-1
    )
    assert shed.reason != ev.OVER_BUDGET_REASON


# Pricing contracts: what a player is owed counts against him.
RATE = ai_evaluator.money_rate(10_000_000, 200_000_000, 1.0, "retooling")


def _paid(rating, now, later, **kw):
    from dataclasses import replace

    return replace(_p(rating, **kw), owed_now=now, owed_later=later)


def _priced(roster, giving, getting, state="retooling", money=RATE, days_left=60):
    return evaluate(roster, giving, getting, state, days_left, 0.08, money=money)


def test_money_rate_by_owner_room_and_state():
    cap = 200_000_000
    tight = ai_evaluator.money_rate(-5_000_000, cap, 1.0, "retooling")
    loose = ai_evaluator.money_rate(80_000_000, cap, 1.0, "retooling")
    assert tight > RATE > loose > 0
    assert ai_evaluator.money_rate(None, cap, 1.0, "retooling") == 0.0
    assert ai_evaluator.money_rate(
        10_000_000, cap, 1.0, "all-in"
    ) < ai_evaluator.money_rate(10_000_000, cap, 1.0, "rebuilding")
    # Salaries grown with the cap cost the same in value.
    assert ai_evaluator.money_rate(10_000_000, cap, 2.0, "retooling") == RATE / 2


def test_without_a_money_rate_contracts_dont_count():
    roster = _roster()
    cheap = _priced(roster, [roster[0]], [_p(64)], money=0.0)
    dear = _priced(roster, [roster[0]], [_paid(64, 30_000_000, 30_000_000)], money=0.0)
    assert cheap.score == dear.score


def test_an_overpaid_player_is_turned_down_for_his_contract():
    roster = _roster()
    fair = _priced(roster, [roster[0]], [_paid(64, 9_000_000, 9_000_000)])
    over = _priced(roster, [roster[0]], [_paid(64, 30_000_000, 30_000_000)])
    assert fair.accept
    assert not over.accept
    assert "contract" in over.reason
    assert over.details["d_money"] < fair.details["d_money"] < 0


def test_sending_away_a_bad_contract_is_worth_something():
    vet = _paid(60, 25_000_000, 25_000_000, age=34)
    roster = _roster() + [vet]
    # A slightly worse, cheap player for him: the savings make it worth it.
    assert _priced(roster, [vet], [_p(57)]).accept
    assert not _judge(roster, [vet], [_p(57)]).accept


def test_a_cheap_star_is_worth_more_than_a_fairly_paid_one():
    roster = _roster()
    cheap = _priced(roster, [roster[0]], [_paid(70, 500_000, 2_000_000)])
    paid = _priced(roster, [roster[0]], [_paid(70, 22_000_000, 22_000_000)])
    assert cheap.score > paid.score > 0


def test_tight_owners_care_more_about_money():
    roster = _roster()
    getting = [_paid(64, 18_000_000, 18_000_000)]
    tight = ai_evaluator.money_rate(-5_000_000, 200_000_000, 1.0, "retooling")
    loose = ai_evaluator.money_rate(80_000_000, 200_000_000, 1.0, "retooling")
    assert _priced(roster, [roster[0]], getting, money=loose).accept
    assert not _priced(roster, [roster[0]], getting, money=tight).accept


def test_a_player_who_wants_out_but_wouldnt_play_costs_nothing_extra():
    """The trade-request discount is a share of what he'd add to the team,
    so a spare arm who wouldn't crack the staff isn't counted against."""
    from dataclasses import replace

    # A full staff of 62s: 5 starters and 11 relievers.
    roster = _roster(62) + [_p(62, pitcher=True) for _ in range(3)]
    spare = _p(55, pitcher=True)
    a = _judge(roster, [], [spare])
    b = _judge(roster, [], [replace(spare, wants_out=True)])
    assert b.score == a.score
