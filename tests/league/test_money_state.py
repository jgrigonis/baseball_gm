# tests/league/test_money_state.py
"""Money states (src/league/money_state.py)."""

from src.league import money_state as ms

CAP = 200_000_000


def test_room_under_the_budget_sets_the_state():
    assert ms.classify(40_000_000, CAP) == "flush"
    assert ms.classify(25_000_000, CAP) == "balanced"
    assert ms.classify(2_000_000, CAP) == "capped-out"
    # A hair over the budget is only capped out.
    assert ms.classify(-6_000_000, CAP) == "capped-out"
    assert ms.classify(-15_000_000, CAP) == "cutting-costs"


def test_the_owners_bank_has_a_say():
    # An empty bank: cutting costs, however much room.
    assert ms.classify(40_000_000, CAP, 0, 200_000_000) == "cutting-costs"
    # Running low: no more than capped out.
    assert ms.classify(40_000_000, CAP, 30_000_000, 200_000_000) == "capped-out"
    # Room but a bank below where it started: balanced, not flush.
    assert ms.classify(40_000_000, CAP, 150_000_000, 200_000_000) == "balanced"
    assert ms.classify(40_000_000, CAP, 250_000_000, 200_000_000) == "flush"


def test_tighter_states_charge_more_for_contracts():
    shares = [ms.money_share(s) for s in ms.STATES]
    assert shares == sorted(shares)
    assert ms.money_share(None) == ms.money_share("balanced")


def test_free_agents_by_state():
    assert ms.hole_margin("flush", 5) < ms.hole_margin("balanced", 5) == 5
    minimum = 780_000
    assert ms.may_sign("balanced", 9_000_000, minimum, False)
    assert ms.may_sign("capped-out", 4_000_000, minimum, True)
    assert not ms.may_sign("capped-out", 4_000_000, minimum, False)
    assert ms.may_sign("cutting-costs", minimum, minimum, False)
    assert not ms.may_sign("cutting-costs", 1_000_000, minimum, True)
    assert ms.sheds("cutting-costs") and not ms.sheds("capped-out")
