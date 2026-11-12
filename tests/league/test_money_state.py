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


def test_payroll_states_for_people():
    from src.league import budget as bg

    cap = 200_000_000
    budget = 260_000_000

    def state(payroll, limit=None):
        s = bg.standing(payroll, cap, budget, limit, front_office=20_000_000)
        return ms.payroll_state(s), ms.payroll_tip(ms.payroll_state(s), s)

    st, tip = state(180_000_000)
    assert st == "under-cap" and "under the $200" in tip and "within" in tip
    st, tip = state(220_000_000)
    assert st == "over-cap" and "over the $200" in tip
    # 250M payroll + 25M tax + 20M FO = 295M, past the 260M budget.
    st, tip = state(250_000_000, limit=300_000_000)
    assert st == "over-budget" and "budget" in tip
    st, tip = state(250_000_000, limit=280_000_000)
    assert st == "over-limit" and "$280" in tip and "limit" in tip
    assert ms.payroll_state(None) is None
    assert list(ms.PAYROLL_LABELS) == list(ms.PAYROLL_STATES)


def test_ai_offers_keep_to_a_persons_owner():
    from src.league import budget as bg

    cap = 200_000_000
    even = round(ms.EVEN_SHARE * cap)

    def room(payroll, limit):
        return ms.person_pay_room(
            bg.standing(payroll, cap, 260_000_000, limit, front_office=20_000_000)
        )

    # Under the budget: what it leaves plus a little, never past the limit.
    s = bg.standing(200_000_000, cap, 260_000_000, 300_000_000, front_office=20_000_000)
    assert room(200_000_000, 300_000_000) == s["budget_payroll_room"] + even
    tight = bg.standing(
        200_000_000, cap, 260_000_000, 241_000_000, front_office=20_000_000
    )
    assert (
        room(200_000_000, 241_000_000)
        == tight["limit_payroll_room"]
        < even + 26_000_000
    )
    # Past the budget: close to even only.
    assert room(250_000_000, 330_000_000) == even
    # Past the limit: nothing that adds salary.
    assert room(250_000_000, 280_000_000) == 0
    assert ms.person_pay_room(None) is None
