# tests/league/test_owner_scoring.py
"""How owners judge a season (src/league/owner_scoring.py)."""

from src.league import owner_scoring as sc
from src.league import owners

MID = owners.clean_traits({})


def season(**kw):
    base = dict(wins=81, losses=81)
    return sc.TeamSeason(**(base | kw))


def test_wins_are_judged_against_the_roster():
    # A .500 season is fine for a middling roster, bad for the best one,
    # great for the worst.
    assert abs(sc.score_dimensions(season(), MID)["wins"]) < 0.01
    assert sc.score_dimensions(season(rank_before=0.0), MID)["wins"] < -0.9
    assert sc.score_dimensions(season(rank_before=1.0), MID)["wins"] > 0.9


def test_ambition_raises_the_bar():
    eager = owners.clean_traits({"ambition": 100})
    assert sc.win_target(0.5, 100) > sc.win_target(0.5, 50)
    assert sc.score_dimensions(season(), eager)["wins"] < 0
    assert sc.expects_playoffs(0.4, 100) and not sc.expects_playoffs(0.4, 50)


def test_october():
    s = sc.score_dimensions
    assert (
        s(season(made_playoffs=True, rounds_won=4, champion=True), MID)["postseason"]
        == 1.0
    )
    assert s(season(rank_before=0.1), MID)["postseason"] == -0.6
    assert s(season(rank_before=0.9), MID)["postseason"] == -0.1
    assert s(season(made_playoffs=True, rounds_won=1), MID)["postseason"] > 0.5


def test_no_money_no_money_scores():
    sc_ = sc.score_dimensions(season(), MID, money=False)
    assert sc_["profit"] is sc_["attendance"] is sc_["fans"] is None


def test_money_is_judged_by_profit_alone():
    # Josh, 2026-11-06: going past the budget only costs profit.
    scores = sc.score_dimensions(season(payroll=110, budget=100), MID)
    assert "budget" not in scores
    assert "budget" not in owners.WEIGHTS


def test_losing_an_icon_and_churn():
    s = sc.score_dimensions(season(icons_lost=2, trades=7), MID)
    assert s["icons"] == -1.0 and s["stability"] == -1.0


def test_the_season_score_follows_the_weights():
    scores = {"wins": 1.0, "profit": -1.0, "budget": None}
    assert sc.season_score(scores, {"wins": 100, "profit": 0}) == 1.0
    assert sc.season_score(scores, {"wins": 0, "profit": 100}) == -1.0
    assert sc.season_score(scores, {"wins": 50, "profit": 50}) == 0.0
    # A dimension that can't be judged doesn't count.
    assert sc.season_score(scores, {"wins": 50, "budget": 100, "profit": 0}) == 1.0


def test_job_security():
    patient = owners.clean_traits({"patience": 100})
    rash = owners.clean_traits({"patience": 0})
    assert sc.grace(100) > sc.grace(0)
    # A bad year costs more under an impatient owner.
    assert sc.next_security(60, -1, rash, False) < sc.next_security(
        60, -1, patient, False
    )
    # An impatient owner gives about one terrible season, a patient one two.
    assert sc.verdict(sc.next_security(sc.grace(0), -1, rash, False)) != "retained"
    # A patient owner keeps a GM through two disasters (on the hot seat, but
    # still in the job: the honeymoon), and one middling year off the hot
    # seat after a single bad one.
    rules = sc.firing_rules("The Long-Gamer")
    one, v1, _ = sc.judge(sc.grace(100), -1, patient, False, sc.Tenure(), rules)
    two, v2, _ = sc.judge(one, -1, patient, False, sc.Tenure(1, -1, one), rules)
    assert v1 != "fired" and v2 != "fired"
    assert one >= sc.HOT_SEAT
    # A title buys time.
    assert sc.next_security(40, 0, MID, True) == 40 + sc.TITLE_BONUS
    assert sc.verdict(sc.FIRE - 1) == "fired" and sc.verdict(sc.FIRE) == "warned"
    assert sc.verdict(80) == "retained"


def test_profit_is_judged_against_the_markets_par():
    # A small market making what a middle owner would there is on par, even
    # at a loss; a big market with a fat margin under its par isn't.
    small = sc.score_dimensions(
        season(payroll=100, budget=100, revenue=200, profit=-10, profit_par=-10), MID
    )["profit"]
    big = sc.score_dimensions(
        season(payroll=100, budget=100, revenue=300, profit=60, profit_par=90), MID
    )["profit"]
    assert small == 0 and big < 0


# ── Firing rules ─────────────────────────────────────────────────────────────

RASH = owners.clean_traits({"patience": 0})


def test_the_honeymoon_holds_a_firing_back():
    rules = sc.FiringRules(honeymoon=2, warn_first=False)
    # A disaster in a GM's first season: past the line, but held at the
    # bottom of the hot seat.
    after, verdict, would = sc.judge(20, -1, RASH, False, sc.Tenure(), rules)
    assert (after, verdict, would) == (sc.FIRE, "warned", True)
    # The second season is still the honeymoon; the third isn't.
    second = sc.Tenure(seasons=1, last_score=-1, last_security=sc.FIRE)
    assert sc.judge(sc.FIRE, -1, RASH, False, second, rules)[1] == "warned"
    third = sc.Tenure(seasons=2, last_score=-1, last_security=sc.FIRE)
    assert sc.judge(sc.FIRE, -1, RASH, False, third, rules)[1] == "fired"


def test_warning_first():
    rules = sc.FiringRules(honeymoon=0, warn_first=True)
    # Safe last time: a crash stops on the hot seat.
    safe = sc.Tenure(seasons=3, last_score=0.2, last_security=60)
    assert sc.judge(20, -1, RASH, False, safe, rules)[:2] == (sc.FIRE, "warned")
    # On the hot seat last time: fired.
    hot = sc.Tenure(seasons=3, last_score=-0.5, last_security=20)
    assert sc.judge(20, -1, RASH, False, hot, rules)[1] == "fired"
    # An ordinary season from the bottom of the hot seat keeps the job.
    bottom = sc.Tenure(seasons=3, last_score=-1, last_security=sc.FIRE)
    assert sc.judge(sc.FIRE, 0, RASH, False, bottom, rules)[1] == "warned"


def test_impatient_owners_fire_without_warning_after_one_season():
    tycoon = sc.firing_rules("The Tycoon")
    assert tycoon.honeymoon == 1 and not tycoon.warn_first
    tenure = sc.Tenure(seasons=1, last_score=0.1, last_security=50)
    assert sc.judge(30, -1, RASH, False, tenure, tycoon)[1] == "fired"
    # Patient owners take longer.
    assert sc.firing_rules("The Long-Gamer").honeymoon == 3
    assert sc.firing_rules("Someone New") == sc.FiringRules()


def test_trend_credit_softens_an_improving_losing_season():
    rules = sc.FiringRules(trend_credit=0.5)
    better = sc.Tenure(seasons=1, last_score=-0.8, last_security=40)
    worse = sc.Tenure(seasons=1, last_score=-0.2, last_security=40)
    assert sc.trended(-0.4, better, rules) == -0.2
    assert sc.trended(-0.4, worse, rules) == -0.4
    assert sc.trended(0.3, better, rules) == 0.3
    a = sc.judge(40, -0.4, MID, False, better, rules)[0]
    b = sc.judge(40, -0.4, MID, False, worse, rules)[0]
    assert a > b


# ── Job offers after a firing (src/league/job_offers.py) ─────────────────────


def test_reputation():
    from src.league import job_offers as jo

    good = [jo.Record(0.5, True, True), jo.Record(0.4, True)]
    bad = [jo.Record(-0.6), jo.Record(-0.5)]
    assert jo.reputation(good, [0]) > jo.reputation(bad, [0])
    # A firing hurts most at first, then fades.
    assert (
        jo.reputation(bad, [0]) < jo.reputation(bad, [2]) < jo.reputation(bad, [3]) + 1
    )
    assert 0 <= jo.reputation(bad, [0, 0, 0]) <= 100


def test_owners_offer_jobs_they_think_the_gm_has_earned():
    from src.league import job_offers as jo

    champs = jo.appeal(0.0, 0.1, 5)
    cellar = jo.appeal(1.0, 0.9, 1)
    assert champs > 80 and cellar < 20
    # An owner unhappy with their AI GM wants a change; a happy one doesn't.
    assert jo.bar(50, MID, 10) < jo.bar(50, MID, 90)
    # Ambitious owners want more, patient ones less.
    assert jo.bar(50, {"ambition": 90}, 50) > jo.bar(50, {"patience": 90}, 50)
    jobs = [
        jo.Job("champs", "The Tycoon", champs),
        jo.Job("cellar", "The Long-Gamer", cellar),
    ]
    assert jo.choose(jobs, 40) == (["cellar"], False)
    # Someone always offers: the keenest owner, even when nobody's bar is met.
    assert jo.choose([jo.Job("a", "", 70), jo.Job("b", "", 60)], 10) == (["b"], True)
    import random

    text = jo.message("The Tycoon", 10, 80, True, random.Random(1))
    assert "anyway" in text or "glamour" in text
    # One screen of offers: no two open the same way, even same-persona owners.
    used: set[str] = set()
    texts = [
        jo.message(a, 80, 50, False, random.Random(i), used)
        for i, a in enumerate(["The Meddler"] * 2 + ["The Tycoon"] * 3)
    ]
    openers = [t.split(".")[0] for t in texts]
    assert len(set(openers)) == 5 and len(set(texts)) == 5


def test_owners_grade_on_a_curve():
    raw = {"a": 0.1, "b": 0.12, "c": 0.08, "d": -0.2}
    c = sc.curved(raw)
    # The worst season stands out, even though raw scores bunch together.
    assert c["d"] < -0.6 and abs(sum(c.values())) < 1e-9
    # Too few teams to grade against: raw.
    assert sc.curved({"a": 0.3, "b": -0.1}) == {"a": 0.3, "b": -0.1}
