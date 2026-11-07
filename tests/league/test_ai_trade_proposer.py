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


def _side(state, extra=(), margin=0.08, untradeable=()):
    roster = _roster() + list(extra)
    return Side(
        team_id=state,
        state=state,
        roster=roster,
        tradeable={a.id for a in roster} - {a.id for a in untradeable},
        margin=margin,
    )


def test_a_contender_buys_a_sellers_veteran_with_a_prospect():
    veteran = _p(70, age=35)
    prospect = _p(65, age=22)
    contender = _side("contending", [prospect])
    seller = _side("rebuilding", [veteran])
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
            side.roster, giving, getting, side.state, 60, side.margin
        ).accept


def test_no_deal_between_two_teams_with_nothing_to_offer():
    assert find_deal(_side("retooling"), _side("retooling"), days_left=60) is None


def test_it_wont_ask_for_a_player_the_other_side_cant_trade():
    veteran = _p(70, age=35)
    seller = _side("rebuilding", [veteran], untradeable=[veteran])
    deal = find_deal(_side("contending", [_p(65, age=22)]), seller, days_left=60)
    assert deal is None or veteran not in deal.get


def test_it_wont_ask_for_a_hurt_player():
    veteran = _p(70, age=35, injured_days=30)
    seller = _side("rebuilding", [veteran])
    deal = find_deal(_side("contending", [_p(65, age=22)]), seller, days_left=60)
    assert deal is None or veteran not in deal.get


def test_it_gives_at_most_two_players():
    star = _p(76, age=30)
    deal = find_deal(
        _side("contending", [_p(60, age=22) for _ in range(4)]),
        _side("rebuilding", [star]),
        days_left=60,
    )
    assert deal is None or len(deal.give) <= 2


def test_it_skips_a_deal_it_was_told_to_avoid():
    veteran = _p(70, age=35)
    prospect = _p(65, age=22)
    contender = _side("contending", [prospect])
    seller = _side("rebuilding", [veteran])
    avoid = {frozenset({veteran.id, prospect.id})}
    deal = find_deal(contender, seller, days_left=60, avoid=avoid)
    assert deal is None or {a.id for a in deal.give + deal.get} not in avoid


# ── Shopping a player (shop_offer) ─────────────────────────────────────────

from src.league.trades.ai_proposer import (  # noqa: E402
    NO_HELP,
    NO_MATCH,
    NO_ROOM,
    ShopOffer,
    shop_offer,
    shop_offer_or_why,
)


def test_a_contender_offers_for_a_shopped_veteran():
    veteran = _p(70, age=31)
    seller = _side("rebuilding", [veteran], margin=0.0)
    prospects = [_p(64, age=22), _p(62, age=23)]
    buyer = _side("contending", prospects)
    offer = shop_offer(buyer, seller, veteran, days_left=60)
    assert offer is not None
    assert 1 <= len(offer.give) <= 2
    # The AI really takes it, by its own margin.
    assert evaluate(
        buyer.roster, offer.give, [veteran], buyer.state, 60, buyer.margin
    ).accept


def test_the_offer_is_the_best_for_the_seller_the_ai_will_take():
    from itertools import combinations

    veteran = _p(70, age=31)
    seller = _side("rebuilding", [veteran], margin=0.0)
    buyer = _side("contending", [_p(64, age=22), _p(62, age=23), _p(60, age=24)])
    offer = shop_offer(buyer, seller, veteran, days_left=60)
    mine = [a for a in buyer.roster if a.id in buyer.tradeable]
    taken = [
        list(g)
        for n in (1, 2)
        for g in combinations(mine, n)
        if evaluate(buyer.roster, list(g), [veteran], "contending", 60, 0.08).accept
    ]

    def for_seller(give):
        return evaluate(seller.roster, [veteran], give, "rebuilding", 60, 0.0).score

    assert for_seller(offer.give) >= max(for_seller(g) for g in taken) - 1e-9


def test_no_offer_when_he_wouldnt_help_them():
    scrub = _p(50)
    seller = _side("retooling", [scrub], margin=0.0)
    assert shop_offer(_side("contending"), seller, scrub, days_left=60) is None


def test_blocked_players_arent_offered():
    veteran = _p(70, age=31)
    prospect = _p(66, age=22)
    seller = _side("rebuilding", [veteran], margin=0.0)
    buyer = _side("contending", [prospect])
    offer = shop_offer(buyer, seller, veteran, 60, blocked={prospect.id})
    assert offer is None or prospect not in offer.give


def _priced(rating, salary, age=27):
    from dataclasses import replace

    return replace(_p(rating, age=age), salary=salary)


def test_salary_sent_back_counts_toward_the_budget():
    """A team that can't add his whole salary can still offer players whose
    pay makes room for it."""
    veteran = _priced(70, 10_000_000, age=31)
    seller = _side("rebuilding", [veteran], margin=0.0)
    prospects = [_priced(64, 9_000_000, age=22), _priced(62, 9_500_000, age=23)]
    buyer = _side("contending", prospects)
    buyer.pay_room = 2_000_000
    offer = shop_offer(buyer, seller, veteran, days_left=60)
    assert offer is not None
    added = veteran.salary - sum(a.salary for a in offer.give)
    assert added <= buyer.pay_room


def test_why_there_is_no_offer():
    scrub = _p(50)
    seller = _side("retooling", [scrub], margin=0.0)
    assert shop_offer_or_why(_side("contending"), seller, scrub, 60) == NO_HELP

    veteran = _priced(70, 10_000_000, age=31)
    seller = _side("rebuilding", [veteran], margin=0.0)
    cheap = [_p(64, age=22), _p(62, age=23)]
    buyer = _side("contending", cheap)
    buyer.pay_room = 1_000_000
    assert shop_offer_or_why(buyer, seller, veteran, 60) == NO_ROOM

    # Wants him, but has nothing the seller would want for him.
    buyer = _side("contending", untradeable=())
    buyer.tradeable = set()
    assert shop_offer_or_why(buyer, seller, veteran, 60) == NO_MATCH


def test_when_no_deal_works_the_closest_package_comes_back_short():
    """A team that wants him but turns down every package the seller would
    want shows the one it came closest to taking, marked short."""
    veteran = _p(64, age=31)
    seller = _side("rebuilding", [veteran], margin=0.0)
    stars = [_p(75, age=24), _p(73, age=25)]
    buyer = _side("contending", stars, margin=0.5)
    buyer.tradeable = {a.id for a in stars}
    offer = shop_offer_or_why(buyer, seller, veteran, 60)
    assert isinstance(offer, ShopOffer) and offer.short
    assert offer.give and all(a in stars for a in offer.give)
    assert not evaluate(
        buyer.roster, offer.give, [veteran], buyer.state, 60, buyer.margin
    ).accept
    # ...and it's no offer to take.
    assert shop_offer(buyer, seller, veteran, 60) is None
