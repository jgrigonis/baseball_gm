# tests/league/test_hr_derby.py
"""The Home Run Derby's rules (src/league/hr_derby.py): the field, the
bracket, a round and the whole derby."""

import random

from src.league import all_star, hr_derby


def _hitter(i, hr, power=70, contact=50):
    return {
        "player_id": f"h{i}",
        "name": f"Hitter {i}",
        "team_id": "t",
        "bat_home_runs": hr,
        "power": power,
        "contact": contact,
    }


def test_the_field_is_the_top_home_run_hitters_seeded():
    hitters = [_hitter(i, 30 - i) for i in range(12)]
    field = hr_derby.field(hitters, set())
    assert [h["player_id"] for h in field] == [f"h{i}" for i in range(8)]
    assert [h["seed"] for h in field] == list(range(1, 9))


def test_hurt_hitters_sit_out_and_ties_go_to_power():
    hitters = [_hitter(0, 30), _hitter(1, 20, power=60), _hitter(2, 20, power=90)]
    hitters += [_hitter(i, 10) for i in range(3, 12)]
    field = hr_derby.field(hitters, {"h0"})
    assert [h["player_id"] for h in field[:2]] == ["h2", "h1"]


def test_a_small_league_gets_a_smaller_bracket():
    assert len(hr_derby.field([_hitter(i, 5) for i in range(6)], set())) == 4
    assert len(hr_derby.field([_hitter(0, 5), _hitter(1, 0)], set())) == 0


def test_the_bracket_keeps_the_top_seeds_apart():
    assert hr_derby.first_round(8) == [(1, 8), (4, 5), (2, 7), (3, 6)]
    assert hr_derby.first_round(4) == [(1, 4), (2, 3)]
    assert hr_derby.first_round(2) == [(1, 2)]


def test_round_names():
    assert hr_derby.round_name(8) == "Quarterfinals"
    assert hr_derby.round_name(4) == "Semifinals"
    assert hr_derby.round_name(2) == "Final"


def test_power_hits_more_home_runs():
    assert hr_derby.hr_chance(95, 50) > hr_derby.hr_chance(50, 50)
    assert 0.2 <= hr_derby.hr_chance(0, 0) and hr_derby.hr_chance(100, 100) <= 0.75
    rng = random.Random(1)
    big = sum(hr_derby.swings(_hitter(0, 0, 95), rng, outs=10)[0] for _ in range(200))
    small = sum(hr_derby.swings(_hitter(0, 0, 40), rng, outs=10)[0] for _ in range(200))
    assert big > small


def test_a_round_ends_after_ten_outs():
    rng = random.Random(3)
    h = _hitter(0, 0)
    homers, longest = hr_derby.swings(h, rng, outs=hr_derby.OUTS_PER_ROUND)
    assert homers >= 0 and (longest > 300 or homers == 0)


def test_a_tie_goes_to_a_swing_off():
    for seed in range(200):
        lines = hr_derby.matchup(_hitter(1, 9), _hitter(2, 8), random.Random(seed))
        a, b = lines
        if a["swingoff"] is not None:
            assert a["homers"] == b["homers"] and b["swingoff"] is not None
            assert a["won"] != b["won"]
            return
    raise AssertionError("no tie in 200 matchups")


def test_the_whole_derby():
    field = hr_derby.field([_hitter(i, 30 - i) for i in range(8)], set())
    lines = hr_derby.run(field, random.Random(7))
    rounds = {}
    for r in lines:
        rounds.setdefault(r["round"], []).append(r)
    assert [len(rounds[n]) for n in (1, 2, 3)] == [8, 4, 2]
    for rnd in rounds.values():
        for m in {r["match"] for r in rnd}:
            assert sum(r["won"] for r in rnd if r["match"] == m) == 1
    # Round 2's hitters are round 1's winners.
    assert {r["player_id"] for r in rounds[2]} == {
        r["player_id"] for r in rounds[1] if r["won"]
    }


def test_the_derby_is_the_day_before_the_game():
    w = all_star.Window("2025-06-01", "2025-06-14", "2025-06-19")
    assert hr_derby.derby_date(w) == "2025-06-16"
    assert all_star.game_date(w) == "2025-06-17"
