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
    NO_VALUE,
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


def test_a_player_whose_contract_costs_more_than_he_helps():
    from dataclasses import replace

    from src.league.trades import ai_evaluator

    pricey = replace(_p(61, age=33), owed_now=24_000_000, owed_later=24_000_000)
    seller = _side("retooling", [pricey], margin=0.0)
    buyer = _side("retooling")
    assert shop_offer_or_why(buyer, seller, pricey, 60) != NO_VALUE
    buyer.money = ai_evaluator.money_rate("capped-out", 1.0, "retooling")
    assert shop_offer_or_why(buyer, seller, pricey, 60) == NO_VALUE


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


# ── Dumping salary (dump_offer_or_why) ──────────────────────────────────────
from src.league.trades.ai_proposer import (  # noqa: E402
    NO_SAVING,
    DumpOffer,
    dump_offer_or_why,
)


def test_a_team_takes_a_useful_player_alone_for_a_throw_in():
    regular = _priced(64, 12_000_000, age=29)
    seller = _side("rebuilding", [regular], margin=0.0)
    filler = _priced(40, 0, age=24)
    buyer = _side("contending", [filler])
    offer = dump_offer_or_why(buyer, seller, regular, days_left=60)
    assert isinstance(offer, DumpOffer)
    assert offer.add == []
    assert offer.give == [filler]
    assert offer.saved == 12_000_000


def test_a_player_who_wouldnt_help_them_needs_a_sweetener():
    scrub = _priced(50, 8_000_000)
    prospect = _p(66, age=22)
    seller = _side("rebuilding", [scrub, prospect], margin=0.0)
    buyer = _side("contending", [_priced(40, 0)])
    offer = dump_offer_or_why(buyer, seller, scrub, days_left=60)
    assert isinstance(offer, DumpOffer)
    assert len(offer.add) == 1 and offer.add[0] is not scrub
    assert offer.saved >= 8_000_000


def test_no_dump_past_the_owners_budget():
    regular = _priced(64, 12_000_000, age=29)
    seller = _side("rebuilding", [regular], margin=0.0)
    buyer = _side("contending", [_priced(40, 0)])
    buyer.pay_room = 1_000_000
    assert dump_offer_or_why(buyer, seller, regular, 60) == NO_ROOM


def test_no_dump_with_nothing_to_add():
    scrub = _priced(45, 8_000_000)
    seller = _side("rebuilding", [scrub], margin=0.0)
    seller.tradeable = {scrub.id}
    buyer = _side("contending", [_priced(40, 0)])
    assert dump_offer_or_why(buyer, seller, scrub, 60) == NO_MATCH


def test_no_dump_that_sends_back_as_much_salary():
    cheap = _priced(64, 900_000, age=29)
    seller = _side("rebuilding", [cheap], margin=0.0)
    seller.tradeable = {cheap.id}
    throw = _priced(40, 1_700_000)
    buyer = _side("contending", [throw])
    buyer.tradeable = {throw.id}
    assert dump_offer_or_why(buyer, seller, cheap, 60) == NO_SAVING


# ── Absorbing salary (absorb_offer_or_why) ──────────────────────────────────
from src.league.trades.ai_proposer import (  # noqa: E402
    NO_BIG,
    NO_LIMIT,
    NO_USE,
    AbsorbOffer,
    absorb_offer_or_why,
)


def _owed(rating, salary, age=27):
    from dataclasses import replace

    return replace(
        _p(rating, age=age), salary=salary, owed_now=salary, owed_later=salary
    )


def _tight(side):
    from src.league.trades import ai_evaluator

    side.pay_room = 0
    side.money = ai_evaluator.money_rate("capped-out", 1.0, side.state)
    return side


def test_a_team_sends_a_big_contract_it_would_rather_be_rid_of():
    scrub = _owed(45, 990_000)
    seller = _side("contending", [scrub], margin=0.0)
    overpaid = _owed(64, 22_000_000, age=32)
    buyer = _tight(_side("rebuilding", [overpaid]))
    offer = absorb_offer_or_why(buyer, seller, scrub, days_left=60)
    assert isinstance(offer, AbsorbOffer)
    assert overpaid in offer.give
    assert offer.added >= 22_000_000 - 990_000
    assert offer.score > 0


def test_no_absorb_without_anyone_paid_more():
    pricey = _owed(45, 30_000_000)
    seller = _side("contending", [pricey], margin=0.0)
    buyer = _tight(_side("rebuilding", [_owed(64, 22_000_000, age=32)]))
    assert absorb_offer_or_why(buyer, seller, pricey, 60) == NO_BIG


def test_no_absorb_when_money_doesnt_matter_to_them():
    scrub = _owed(45, 990_000)
    seller = _side("contending", [scrub], margin=0.0)
    buyer = _side("rebuilding", [_owed(64, 22_000_000, age=32)])
    assert absorb_offer_or_why(buyer, seller, scrub, 60) == NO_MATCH


def test_no_absorb_of_contracts_that_wouldnt_help_you():
    scrub = _owed(45, 990_000)
    seller = _side("contending", [scrub], margin=0.0)
    dead = _owed(40, 22_000_000, age=36)
    buyer = _tight(_side("rebuilding", [dead]))
    buyer.tradeable = {dead.id}
    assert absorb_offer_or_why(buyer, seller, scrub, 60) == NO_USE


def test_no_absorb_past_your_owners_limit():
    scrub = _owed(45, 990_000)
    seller = _side("contending", [scrub], margin=0.0)
    buyer = _tight(_side("rebuilding", [_owed(64, 22_000_000, age=32)]))
    offer = absorb_offer_or_why(buyer, seller, scrub, 60, fits=lambda added: False)
    assert offer == NO_LIMIT
    offer = absorb_offer_or_why(
        buyer, seller, scrub, 60, fits=lambda added: added < 30_000_000
    )
    assert isinstance(offer, AbsorbOffer)


def test_a_trade_request_doesnt_sink_a_depth_arm_nobody_would_miss():
    """A reliever who asked out, but wouldn't crack their staff, adds
    little to them, so the trade-request discount takes little off: a team
    with a spot for him takes him alone, no sweetener needed."""
    from dataclasses import replace

    arm = replace(_priced(57, 990_000, age=21), is_pitcher=True, wants_out=True)
    prospect = _p(66, age=22)
    seller = _side("retooling", [arm, prospect], margin=0.0)
    seller.tradeable = {arm.id, prospect.id}
    buyer = _side("contending", [_priced(40, 0)])
    offer = dump_offer_or_why(buyer, seller, arm, days_left=60)
    assert isinstance(offer, DumpOffer)
    assert offer.add == []


def test_sweeteners_are_players_the_team_would_want():
    """Spare depth the seller wouldn't miss is no use to them either: the
    sweetener it asks for is one it would want, even past the first few
    cheapest."""
    from src.league.trades import ai_proposer

    scrub = _priced(50, 8_000_000)
    spares = [_p(45, age=30) for _ in range(ai_proposer.MAX_SWEETENERS + 4)]
    prospect = _p(66, age=22)
    seller = _side("rebuilding", [scrub, prospect, *spares], margin=0.0)
    seller.tradeable = {scrub.id, prospect.id} | {a.id for a in spares}
    buyer = _side("contending", [_priced(40, 0)])
    offer = dump_offer_or_why(buyer, seller, scrub, days_left=60)
    assert isinstance(offer, DumpOffer)
    assert offer.add == [prospect]


def test_a_team_shedding_salary_only_finds_deals_that_lower_its_payroll():
    """A team cutting costs (src/league/money_state.py) won't take a deal
    that sends back as much salary as it sends out."""
    veteran = _owed(70, 8_000_000, age=35)
    prospect = _owed(65, 2_000_000, age=22)
    contender = _side("contending", [prospect])
    seller = _side("rebuilding", [veteran])
    assert find_deal(contender, seller, days_left=60) is not None
    assert find_deal(contender, seller, days_left=60, shed=True) is None
    # The other way round, the deal sheds salary.
    deal = find_deal(seller, contender, days_left=60, shed=True)
    assert deal is not None and deal.give == [veteran]
