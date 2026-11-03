import random
from collections import Counter

from src.player import jersey_numbers as jn


def test_every_number_from_0_to_99_plus_00():
    assert set(jn.NUMBERS) == {str(n) for n in range(100)} | {"00"}


def test_prefs_are_a_favorite_and_distinct_fallbacks():
    for i in range(200):
        prefs = jn.prefs_for(f"p{i}")
        assert len(prefs) == 1 + jn.FALLBACKS
        assert len(set(prefs)) == len(prefs)
        assert all(n in jn.NUMBER_WEIGHTS for n in prefs)


def test_prefs_are_the_same_every_time_for_a_player():
    assert jn.prefs_for("abc") == jn.prefs_for("abc")


def test_favorites_follow_the_curve():
    favs = Counter(jn.prefs_for(f"p{i}")[0] for i in range(20000))
    # Low numbers beat high ones by a lot, 13 dips, 42 isn't retired.
    assert favs["7"] > 5 * favs["62"]
    assert favs["5"] > favs["13"] * 1.5
    assert favs["13"] < favs["12"] and favs["13"] < favs["14"]
    assert favs["42"] > favs["50"]
    assert sum(favs[str(n)] for n in range(1, 30)) > 0.6 * 20000
    assert sum(favs[str(n)] for n in range(70, 100)) < 0.02 * 20000


def test_fallbacks_lean_toward_the_favorites_cousins():
    hits = total = 0
    for i in range(3000):
        prefs = jn.prefs_for(f"p{i}")
        cousins = jn._cousins(prefs[0])
        hits += sum(1 for n in prefs[1:] if n in cousins)
        total += len(prefs) - 1
    assert hits / total > 0.2


def test_cousins():
    assert {"17", "27", "77"} <= jn._cousins("7")
    assert "42" in jn._cousins("24")
    assert "7" not in jn._cousins("7")


def test_open_number_takes_the_first_free_one():
    rng = random.Random(1)
    assert jn.open_number(["7", "17", "27"], {"7"}, rng) == "17"


def test_open_number_falls_back_to_any_free_number():
    rng = random.Random(1)
    n = jn.open_number(["7"], {"7"}, rng)
    assert n != "7" and n in jn.NUMBER_WEIGHTS


def test_seniority_keeps_the_number_unless_the_holder_defers():
    rng = random.Random(1)
    holders = {"7": "vet", "17": "other"}
    assert jn.choose_number(["7", "17", "27"], holders, rng) == ("27", None)
    assert jn.choose_number(
        ["7", "17"], holders, rng, will_defer=lambda h: h == "vet"
    ) == ("7", "vet")


def test_who_defers():
    yes = dict(
        holder_age=35, holder_rating=60, newcomer_rating=75, newcomer_team_rank=1
    )
    always = random.Random(0)
    always.random = lambda: 0.0
    assert jn.defers(**yes, rng=always)
    assert not jn.defers(**{**yes, "holder_age": 30}, rng=always)
    assert not jn.defers(**{**yes, "newcomer_rating": 65}, rng=always)  # not a star
    assert not jn.defers(
        **{**yes, "holder_rating": 70}, rng=always
    )  # not clearly better
    assert not jn.defers(**{**yes, "newcomer_team_rank": 5}, rng=always)
    never = random.Random(0)
    never.random = lambda: 0.99
    assert not jn.defers(**yes, rng=never)


def test_assign_by_seniority():
    rng = random.Random(1)
    out = jn.assign_by_seniority([("a", ["7", "8"]), ("b", ["7", "9"])], rng)
    assert out == {"a": "7", "b": "9"}
