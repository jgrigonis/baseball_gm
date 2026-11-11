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


def test_homegrown_talk_names_the_count_and_what_most_teams_have():
    season = om.facts(
        {"homegrown_players": 2, "roster_players": 39, "league_homegrown": 0.18}
    )
    w = owners.clean_weights({"wins": 90, "homegrown": 80})
    # As the worry at the end of a pleased check-in.
    body = om.checkin(
        {"wins": 0.8, "homegrown": -0.6}, w, FIELDS, random.Random(2), mood=0.3,
        season=season,
    )  # fmt: skip
    assert body.endswith(
        "But I'd like to see more players we drafted on this roster. Only two of"
        " our 39 players came through our own draft. Most teams have about seven."
    )
    # As the lead line.
    body = om.checkin(
        {"homegrown": -0.8}, owners.clean_weights({"homegrown": 100}), FIELDS,
        random.Random(3), mood=-0.4, season=season,
    )  # fmt: skip
    assert "Only two of our 39 players came through our own draft." in body
    none = om.facts({"homegrown_players": 0, "roster_players": 40})
    assert om._homegrown(none) == (
        "Not one player on our 40-man roster came through our own draft."
    )


def test_homegrown_near_the_league_isnt_a_shortfall():
    # 32 of 40 when most teams have 33: an ok line, not a complaint.
    season = om.facts(
        {"homegrown_players": 32, "roster_players": 40, "league_homegrown": 0.825}
    )
    assert om._homegrown(season, "ok") == (
        "32 of our 40 players came through our own draft, about what most teams have."
    )
    # Short of most teams but not by enough to be bad: no "Only".
    short = om.facts(
        {"homegrown_players": 29, "roster_players": 40, "league_homegrown": 0.825}
    )
    assert om._homegrown(short, "ok") == (
        "29 of our 40 players came through our own draft. Most teams have about 33."
    )
    assert om._homegrown(short, "bad").startswith("Only 29 of our 40")


def _three_checkins(scores, w, seasons, mood=0.3):
    earlier: list[str] = []
    for i, season in enumerate(seasons):
        body = om.checkin(
            scores, w, FIELDS, random.Random(i), recent=earlier[:4], mood=mood,
            season=season, earlier=earlier,
        )  # fmt: skip
        earlier.insert(0, body)
    return earlier[::-1]


HOMEGROWN = {"homegrown_players": 35, "roster_players": 40, "league_homegrown": 0.72}


def test_checkins_dont_repeat_a_fact_that_hasnt_changed():
    w = owners.clean_weights({"homegrown": 100, "stars": 70, "icons": 60})
    scores = {"homegrown": 0.8, "stars": 0.5, "icons": 0.0}
    season = om.facts(HOMEGROWN)
    bodies = _three_checkins(scores, w, [season] * 3)
    said = [b for b in bodies if "35 of our 40 players" in b]
    assert len(said) == 1, bodies
    # Different lines each time, and each still opens pleased and leads good.
    assert len(set(bodies)) == 3
    for b in bodies:
        assert any(
            b.startswith(om._fill(o, FIELDS)) for o in om.CHECKIN_OPEN["pleased"]
        )
        assert not _lines_in(b, {k: v["bad"] for k, v in om.NOTES.items()})


def test_a_fact_that_moved_is_said_again():
    w = owners.clean_weights({"homegrown": 100})
    scores = {"homegrown": 0.8}
    later = om.facts({**HOMEGROWN, "homegrown_players": 38})
    bodies = _three_checkins(scores, w, [om.facts(HOMEGROWN), later])
    assert "35 of our 40 players" in bodies[0]
    assert "38 of our 40 players" in bodies[1]


def test_a_lone_topic_comes_back_as_a_callback():
    w = owners.clean_weights({"homegrown": 100})
    bodies = _three_checkins({"homegrown": 0.8}, w, [om.facts(HOMEGROWN)] * 2)
    assert "came through our own draft" not in bodies[1]
    assert _lines_in(bodies[1], {"g": om.AGAIN["homegrown"]["good"]})


def test_a_topic_whose_tone_turned_is_news():
    w = owners.clean_weights({"wins": 100, "stars": 60})
    season = om.facts({"wins": 20, "losses": 10})
    first = om.checkin({"wins": 0.8, "stars": 0.4}, w, FIELDS, random.Random(1),
                       mood=0.3, season=season)  # fmt: skip
    second = om.checkin(
        {"wins": -0.8, "stars": 0.4}, w, FIELDS, random.Random(1), mood=-0.3,
        season=om.facts({"wins": 22, "losses": 16}), earlier=[first],
    )  # fmt: skip
    assert "We're 22-16." in second


def test_a_winning_team_below_its_target_isnt_called_a_loser():
    # Josh, 2026-11-11: at 46-37 a strong roster's owner said "I've seen
    # enough losses for one year."
    w = owners.clean_weights({"wins": 100, "icons": 60})
    season = om.facts({"wins": 46, "losses": 37})
    for seed in range(20):
        body = om.checkin(
            {"wins": -1.0, "icons": 0.1}, w, FIELDS, random.Random(seed),
            mood=-0.2, season=season,
        )  # fmt: skip
        assert "We're 46-37." in body
        assert not _lines_in(body, {"w": om.NOTES["wins"]["bad"]}), body
        assert _lines_in(body, {"w": om.WINS_BY_RECORD["winning"]["notes"]["bad"]})
    again = om.checkin(
        {"wins": -1.0}, w, FIELDS, random.Random(1), mood=-0.2,
        season=om.facts({"wins": 48, "losses": 38}), earlier=[body],
    )  # fmt: skip
    assert _lines_in(again, {"w": om.WINS_BY_RECORD["winning"]["again"]["bad"]})


def test_a_losing_team_beating_its_target_isnt_called_a_winner():
    w = owners.clean_weights({"wins": 100})
    season = om.facts({"wins": 38, "losses": 45})
    body = om.checkin(
        {"wins": 0.8}, w, FIELDS, random.Random(2), mood=0.3, season=season
    )
    assert not _lines_in(body, {"w": om.NOTES["wins"]["good"]}), body
    assert _lines_in(body, {"w": om.WINS_BY_RECORD["losing"]["notes"]["good"]})
