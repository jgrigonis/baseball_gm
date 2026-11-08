# tests/league/test_owner_message_rules.py
"""What owners say, and their mood (src/league/owner_messages.py)."""

import random

from src.league import owner_messages as om
from src.league import owners

FIELDS = {
    "gm": "Sam",
    "team": "Boston Beacons",
    "rival": "Moscow Cossacks",
    "budget": "$150M",
}


def test_mood_words():
    assert om.mood_word(0.9) == "thrilled"
    assert om.mood_word(0.0) == "content"
    assert om.mood_word(-0.5) == "frustrated"
    assert om.mood_word(-1.0) == "furious"


def test_temper_moves_mood_faster():
    assert om.next_mood(0, -1, 90) < om.next_mood(0, -1, 10) < 0


def test_the_preseason_memo_says_what_they_want_without_numbers():
    pincher = owners.clean_weights({"budget": 100, "profit": 95, "stars": 0})
    memo = om.preseason(pincher, FIELDS, random.Random(1))
    assert "$150M" in memo  # the budget is theirs to know
    assert not any(ch.isdigit() for ch in memo.replace("$150M", ""))
    grudge = owners.clean_weights({"rivalry": 100})
    assert "Moscow Cossacks" in om.preseason(grudge, FIELDS, random.Random(2))


def test_no_money_talk_without_budgets():
    pincher = owners.clean_weights({"budget": 100, "profit": 95})
    memo = om.preseason(pincher, FIELDS, random.Random(1), money=False)
    assert "$150M" not in memo and "money" not in memo.lower()


def test_checkins_follow_the_worst_and_best():
    weights = owners.clean_weights({"wins": 100})
    bad = om.checkin({"wins": -1.0}, weights, FIELDS, random.Random(3))
    assert any(line in bad for line in om.NOTES["wins"]["bad"])


def test_the_review_ends_on_job_security():
    weights = owners.clean_weights({})
    text = om.review({"wins": -1.0}, weights, FIELDS, "warned", random.Random(4))
    assert any(line in text for line in om.REVIEW_CLOSE["warned"])


def test_every_template_fills():
    fields = {**FIELDS, "payroll": "$200M"}
    asides = {k: tuple(v.values()) for k, v in om.ASIDES.items()}
    tables = (om.WANTS, *om.NOTES.values(), asides, om.TRADE_REACTIONS)
    for table in (*tables, {"over": om.OVER_BUDGET}, om.CHECKIN_OPEN, om.CHECKIN_TURN):
        for lines in table.values():
            for line in lines:
                assert "{" not in om._fill(line, fields)


def test_checkin_openers_dont_repeat_recent_ones():
    weights = {"wins": 100}
    recent: list[str] = []
    openers = []
    for seed in range(5):
        body = om.checkin(
            {"wins": 0.0}, weights, FIELDS, random.Random(seed), recent=recent
        )
        opener = next(
            om._fill(o, FIELDS)
            for o in om.CHECKIN_OPEN["content"]
            if body.startswith(om._fill(o, FIELDS))
        )
        openers.append(opener)
        recent = [body, *recent][:4]
    assert len(set(openers)) == len(openers)


# An Absentee-like owner: money and a steady roster first, then wins.
ABSENTEE = dict(zip(owners.WEIGHTS, owners.ARCHETYPES_BY_NAME["The Absentee"].weights))


def _lines_in(body: str, table: dict) -> list[str]:
    return [line for lines in table.values() for line in lines if line in body]


def test_an_uneasy_owner_leads_with_the_worry_and_the_bright_spot_is_an_aside():
    scores = {"wins": -0.9, "stability": 0.25, "profit": -0.1, "postseason": -0.1}
    season = om.facts({"wins": 41, "losses": 52, "trades": 0})
    for seed in range(20):
        body = om.checkin(
            scores, ABSENTEE, FIELDS, random.Random(seed), mood=-0.2, season=season
        )
        assert any(
            body.startswith(om._fill(o, FIELDS)) for o in om.CHECKIN_OPEN["uneasy"]
        )
        assert "We're 41-52." in body  # says what it's reacting to
        # Never praise as a full line next to the complaint.
        assert not _lines_in(body, {k: v["good"] for k, v in om.NOTES.items()})


def test_good_news_under_a_bad_mood_says_things_turned():
    scores = {"wins": 0.6, "stability": 0.25}
    body = om.checkin(scores, ABSENTEE, FIELDS, random.Random(1), mood=-0.5)
    assert any(body.startswith(o) for o in om.CHECKIN_TURN["up"])


def test_a_pleased_owner_saves_the_worry_for_last():
    scores = {"wins": 0.8, "stability": -0.6}
    w = owners.clean_weights({"wins": 90, "stability": 80})
    body = om.checkin(scores, w, FIELDS, random.Random(2), mood=0.3)
    assert body.endswith(om.ASIDES["stability"]["bad"])


def test_money_lines_name_the_payroll_against_the_budget():
    season = om.facts({"profit": -50_000_000}, 298_500_000, 185_300_000)
    pincher = owners.clean_weights({"profit": 100})
    body = om.checkin(
        {"profit": -1.0}, pincher, FIELDS, random.Random(3), mood=-0.4, season=season
    )
    assert "Payroll's at $298.5M. I gave you $185.3M for players." in body
    season = om.facts({"profit": -5_000_000})
    body = om.checkin(
        {"profit": -0.5}, pincher, FIELDS, random.Random(3), mood=-0.4, season=season
    )
    assert "we lose money this year" in body


def test_the_review_says_how_the_year_finished():
    season = om.facts({"wins": 70, "losses": 92, "trades": 2}, final=True)
    w = owners.clean_weights({"wins": 100, "stability": 60})
    text = om.review(
        {"wins": -0.8, "stability": -0.2},
        w,
        FIELDS,
        "fine",
        random.Random(4),
        True,
        season,
    )
    assert "We finished 70-92." in text and "Two trades this year." in text
