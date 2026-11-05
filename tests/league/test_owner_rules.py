# tests/league/test_owners.py
"""The owner library's pure rules (src/league/owners.py)."""

import random
from collections import Counter

from src.league import owners


def test_the_seed_has_every_archetype_with_every_dial():
    lib = owners.seed()
    assert len(lib) == len(owners.ARCHETYPES) * owners.PER_ARCHETYPE
    assert len({o["name"] for o in lib}) == len(lib)
    for o in lib:
        assert set(o["weights"]) == set(owners.WEIGHTS)
        assert set(o["traits"]) == set(owners.TRAIT_KEYS)
        assert all(
            0 <= v <= 100 for v in [*o["weights"].values(), *o["traits"].values()]
        )


def test_the_seed_is_the_same_every_time():
    assert owners.seed() == owners.seed()


def test_misers_and_spenders():
    lib = owners.seed()
    spend = {
        a: [o["traits"]["spending"] for o in lib if o["archetype"] == a]
        for a in ("The Tycoon", "The Penny-Pincher")
    }
    assert min(spend["The Tycoon"]) > 80
    assert max(spend["The Penny-Pincher"]) < 20


def test_every_archetype_says_what_it_wants_without_numbers():
    for a in owners.ARCHETYPES:
        assert a.wants and not any(ch.isdigit() for ch in a.wants)
        assert owners.wants(a.name) == a.wants
    assert owners.wants("Someone new") == ""


def test_top_dimensions_heaviest_first():
    w = dict.fromkeys(owners.WEIGHTS, 10) | {"rivalry": 95, "stars": 80}
    assert owners.top_dimensions(w, 2) == ["rivalry", "stars"]


def test_clean_fills_gaps_and_clamps():
    w = owners.clean_weights({"wins": 140, "profit": -3, "stars": "x"})
    assert w["wins"] == 100 and w["profit"] == 0 and w["stars"] == 50
    assert w["future"] == 50


def _pool():
    return [
        {"id": str(i), "archetype": o["archetype"], "chance": o["chance"]}
        for i, o in enumerate(owners.seed())
    ]


def test_big_markets_draw_more_tycoons_small_ones_more_misers():
    pool = _pool()
    rng = random.Random(1)

    def draws(market):
        return Counter(
            owners.choose(pool, set(), market, rng)["archetype"] for _ in range(4000)
        )

    big, small = draws(5), draws(1)
    assert big["The Tycoon"] > 1.5 * small["The Tycoon"]
    assert small["The Penny-Pincher"] > 1.5 * big["The Penny-Pincher"]
    # A mild tilt: a small market still draws Tycoons.
    assert small["The Tycoon"] > 0


def test_choose_skips_taken_and_retired_owners():
    pool = [
        {"id": "a", "archetype": "The Tycoon", "chance": 50},
        {"id": "b", "archetype": "The Tycoon", "chance": 0},
        {"id": "c", "archetype": "The Showman", "chance": 50},
    ]
    rng = random.Random(3)
    assert {owners.choose(pool, {"a"}, 3, rng)["id"] for _ in range(50)} == {"c"}
    # Everyone pickable taken: repeats allowed, still never chance 0.
    assert owners.choose(pool, {"a", "c"}, 3, rng)["id"] in {"a", "c"}
    assert owners.choose([pool[1]], set(), 3, rng) is None


def test_rival_is_usually_in_the_division():
    rng = random.Random(5)
    picks = Counter(
        owners.choose_rival("t1", ["t1", "t2"], ["t1", "t2", "t3", "t4"], rng)
        for _ in range(1000)
    )
    assert "t1" not in picks
    assert picks["t2"] > 700
    assert owners.choose_rival("t1", [], ["t1", "t3"], rng) == "t3"
    assert owners.choose_rival("t1", [], ["t1"], rng) is None
