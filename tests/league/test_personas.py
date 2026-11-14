# tests/league/test_personas.py
"""GM personas: the dials, the seeded library, the weighted pick and what the
dials set."""

import random
from collections import Counter

from src.league import personas
from src.league.personas import Leanings
from src.team.manager_profile import ManagerProfile


def test_seed_makes_over_100_unique_personas():
    library = personas.seed()
    assert len(library) >= 100
    assert len({p["name"] for p in library}) == len(library)
    assert {p["archetype"] for p in library} == {a.name for a in personas.ARCHETYPES}
    for p in library:
        assert p["chance"] == personas.DEFAULT_CHANCE
        assert set(p["dials"]) == set(personas.DIALS)
        assert all(0 <= v <= 100 for v in p["dials"].values())
        assert p["bio"]


def test_seed_is_the_same_every_time():
    assert personas.seed() == personas.seed()


def test_seeded_dials_stay_near_their_archetype():
    for p in personas.seed():
        arch = next(a for a in personas.ARCHETYPES if a.name == p["archetype"])
        for key, center in zip(personas.DIALS, arch.dials):
            assert abs(p["dials"][key] - center) <= personas.JITTER


def test_words_by_band():
    assert personas.word("bullpen_hook", 0) == "long leash"
    assert personas.word("bullpen_hook", 19) == "long leash"
    assert personas.word("bullpen_hook", 20) == "lets starters work"
    assert personas.word("bullpen_hook", 50) == "normal hook"
    assert personas.word("bullpen_hook", 100) == "very quick hook"


def test_describe_lists_every_dial_in_order():
    rows = personas.describe({"risk": 90})
    assert [r["key"] for r in rows] == list(personas.DIALS)
    risk = next(r for r in rows if r["key"] == "risk")
    assert risk["value"] == 90
    assert risk["word"] == "a gambler"
    assert risk["ends"] == ("Cautious", "Gambler")


def test_clean_fills_and_clamps():
    d = personas.clean({"risk": "120", "loyalty": -5, "youth": "junk"})
    assert d["risk"] == 100
    assert d["loyalty"] == 0
    assert d["youth"] == 50
    assert d["analytics"] == 50


def test_word_lists_have_no_gendered_pronouns():
    for _, _, low, high, words in personas.TRAITS:
        for text in (low, high, *words):
            assert not {"he", "his", "him", "she", "her"} & set(text.lower().split())
    for arch in personas.ARCHETYPES:
        assert not {"he", "his", "him", "she", "her"} & set(arch.bio.lower().split())


# ── The pick ─────────────────────────────────────────────────────────────────


def _pool(**chances):
    return [{"id": k, "chance": v} for k, v in chances.items()]


def test_choose_never_picks_chance_zero():
    rng = random.Random(1)
    pool = _pool(a=0, b=50)
    assert {personas.choose(pool, set(), rng)["id"] for _ in range(200)} == {"b"}


def test_choose_weights_by_chance():
    rng = random.Random(2)
    pool = _pool(a=100, b=50)
    picks = Counter(personas.choose(pool, set(), rng)["id"] for _ in range(6000))
    assert 1.8 < picks["a"] / picks["b"] < 2.2


def test_choose_skips_taken_until_every_one_is():
    rng = random.Random(3)
    pool = _pool(a=50, b=50, c=0)
    assert all(personas.choose(pool, {"a"}, rng)["id"] == "b" for _ in range(50))
    # Every pickable one taken: repeats are allowed, still never chance 0.
    assert personas.choose(pool, {"a", "b"}, rng)["id"] in {"a", "b"}


def test_choose_with_nothing_pickable():
    assert personas.choose(_pool(a=0), set(), random.Random()) is None
    assert personas.choose([], set(), random.Random()) is None


# ── What the dials set ───────────────────────────────────────────────────────


def test_neutral_persona_manages_like_the_default_profile():
    settings = personas.profile(personas.NEUTRAL)
    assert ManagerProfile.from_row(settings) == ManagerProfile()


def test_tactical_dials_move_the_settings():
    small = personas.profile({"small_ball": 95})
    assert small["sac_bunt"] == "frequent"
    assert small["baserunning"] == "very-aggressive"
    assert small["lineup_style"] == "speed-first"

    slug = personas.profile({"small_ball": 5, "offense_defense": 90})
    assert slug["sac_bunt"] == "never"
    assert slug["baserunning"] == "very-conservative"
    assert slug["lineup_style"] == "power-first"

    glove = personas.profile({"offense_defense": 10})
    assert glove["lineup_style"] == "defensive"

    quick = personas.profile({"bullpen_hook": 90, "analytics": 70})
    assert quick["starter_usage"] == "75"
    assert quick["tired_starters"] == "protect"
    assert quick["bullpen_pref"] == "deep-pen"

    middle = personas.profile({"bullpen_hook": 50})
    assert middle["starter_usage"] == "85"
    assert middle["bullpen_pref"] == "balanced"

    leash = personas.profile({"bullpen_hook": 10})
    assert leash["starter_usage"] == "105"
    assert leash["bullpen_pref"] == "starter-heavy"
    assert leash["tired_starters"] == "push"

    old = personas.profile({"analytics": 10})
    assert old["lineup_style"] == "traditional"
    assert old["platoon_usage"] == "none"

    modern = personas.profile({"analytics": 90, "loyalty": 20})
    assert modern["closer_usage"] == "best-available"
    assert modern["platoon_usage"] == "aggressive"
    # A loyal modern GM keeps the regulars in.
    assert personas.profile({"analytics": 90, "loyalty": 90})["platoon_usage"] == "none"

    now = personas.profile({"time_horizon": 90})
    assert now["playoff_rotation"] == "3"
    assert now["skip_fifth_starter"] is True


def test_every_seeded_profile_is_valid():
    for p in personas.seed():
        settings = personas.profile(p["dials"])
        profile = ManagerProfile.from_row(settings)
        for key, value in settings.items():
            assert getattr(profile, key) == value, (p["name"], key)


def test_leanings():
    neutral = Leanings()
    assert neutral.lean == 0
    assert neutral.horizon == 0
    assert neutral.margin_factor == 1.0
    assert neutral.activity_factor == 1.0
    assert neutral.stats_weight == 0.5

    bold = Leanings.from_dials(
        {"time_horizon": 100, "risk": 100, "trade_activity": 100}
    )
    assert bold.lean == 1.0
    assert bold.margin_factor == 0.5
    assert bold.activity_factor == 1.5

    patient = Leanings.from_dials({"time_horizon": 0, "risk": 0, "trade_activity": 0})
    assert patient.lean == -1.0
    assert patient.margin_factor == 1.5
    assert patient.activity_factor == 0.5
