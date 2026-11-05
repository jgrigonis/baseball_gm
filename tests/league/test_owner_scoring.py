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
    assert sc_["profit"] is sc_["budget"] is sc_["attendance"] is sc_["fans"] is None


def test_budget_over_hurts_more_than_under_helps():
    under = sc.score_dimensions(season(payroll=90, budget=100), MID)["budget"]
    over = sc.score_dimensions(season(payroll=110, budget=100), MID)["budget"]
    assert 0 < under <= 0.5 and over < -under


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
    two = sc.next_security(
        sc.next_security(sc.grace(100), -1, patient, False), -1, patient, False
    )
    assert two >= sc.HOT_SEAT
    # A title buys time.
    assert sc.next_security(40, 0, MID, True) == 40 + sc.TITLE_BONUS
    assert sc.verdict(10) == "fired" and sc.verdict(20) == "warned"
    assert sc.verdict(80) == "retained"
