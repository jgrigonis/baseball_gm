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
    for table in (om.WANTS, *om.NOTES.values(), om.TRADE_REACTIONS):
        for lines in table.values():
            for line in lines:
                assert "{" not in om._fill(line, FIELDS)


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
            for o in om.CHECKIN_OPEN["ok"]
            if body.startswith(om._fill(o, FIELDS))
        )
        openers.append(opener)
        recent = [body, *recent][:4]
    assert len(set(openers)) == len(openers)
