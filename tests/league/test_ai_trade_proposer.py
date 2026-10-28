# tests/league/test_ai_trade_proposer.py
"""How an AI GM looks for a trade to offer (src/league/trades/ai_proposer.py)."""

from itertools import count

from src.league.trades.ai_evaluator import Asset, evaluate
from src.league.trades.ai_proposer import Side, find_deal

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


def _side(stance, extra=(), margin=0.08, untradeable=()):
    roster = _roster() + list(extra)
    return Side(
        team_id=stance,
        stance=stance,
        roster=roster,
        tradeable={a.id for a in roster} - {a.id for a in untradeable},
        margin=margin,
    )


def test_a_contender_buys_a_sellers_veteran_with_a_prospect():
    veteran = _p(70, age=35)
    prospect = _p(65, age=22)
    contender = _side("contender", [prospect])
    seller = _side("seller", [veteran])
    deal = find_deal(contender, seller, days_left=60)
    assert deal is not None
    assert deal.get == [veteran]
    assert prospect in deal.give
    # Both sides take it, each by its own margin.
    for side, giving, getting in (
        (contender, deal.give, deal.get),
        (seller, deal.get, deal.give),
    ):
        assert evaluate(
            side.roster, giving, getting, side.stance, 60, side.margin
        ).accept


def test_no_deal_between_two_teams_with_nothing_to_offer():
    assert find_deal(_side("neutral"), _side("neutral"), days_left=60) is None


def test_it_wont_ask_for_a_player_the_other_side_cant_trade():
    veteran = _p(70, age=35)
    seller = _side("seller", [veteran], untradeable=[veteran])
    deal = find_deal(_side("contender", [_p(65, age=22)]), seller, days_left=60)
    assert deal is None or veteran not in deal.get


def test_it_wont_ask_for_a_hurt_player():
    veteran = _p(70, age=35, injured_days=30)
    seller = _side("seller", [veteran])
    deal = find_deal(_side("contender", [_p(65, age=22)]), seller, days_left=60)
    assert deal is None or veteran not in deal.get


def test_it_gives_at_most_two_players():
    star = _p(76, age=30)
    deal = find_deal(
        _side("contender", [_p(60, age=22) for _ in range(4)]),
        _side("seller", [star]),
        days_left=60,
    )
    assert deal is None or len(deal.give) <= 2


def test_it_skips_a_deal_it_was_told_to_avoid():
    veteran = _p(70, age=35)
    prospect = _p(65, age=22)
    contender = _side("contender", [prospect])
    seller = _side("seller", [veteran])
    avoid = {frozenset({veteran.id, prospect.id})}
    deal = find_deal(contender, seller, days_left=60, avoid=avoid)
    assert deal is None or {a.id for a in deal.give + deal.get} not in avoid
