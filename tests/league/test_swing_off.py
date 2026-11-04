# tests/league/test_swing_off.py
"""The home run swing-off after a tied All-Star or Rookie Game
(src/league/swing_off.py)."""

import random

from src.league import swing_off


def _hitter(i, power=70, contact=50):
    return {
        "player_id": f"h{i}",
        "name": f"Hitter {i}",
        "power": power,
        "contact": contact,
    }


def test_the_best_home_run_hitters_swing():
    players = [_hitter(i, power=40 + 10 * i) for i in range(6)]
    assert [h["player_id"] for h in swing_off.hitters(players)] == ["h5", "h4", "h3"]


def test_three_hitters_three_swings_each_and_someone_wins():
    for seed in range(200):
        sides = {s: [_hitter(f"{s}{i}") for i in range(3)] for s in (1, 2)}
        out = swing_off.play(sides, random.Random(seed))
        for s in (1, 2):
            assert len(out[str(s)]) == 3
            assert all(0 <= h["homers"] <= swing_off.SWINGS for h in out[str(s)])
        w = out["winner"]
        assert swing_off.total(out, w) > swing_off.total(out, 3 - w)
        # Sudden death only when the swings were tied, and every round but
        # the last one tied too.
        rounds = out["sudden_death"]
        if rounds:
            assert sum(h["homers"] for h in out["1"]) == sum(
                h["homers"] for h in out["2"]
            )
            assert all(r["1"] == r["2"] for r in rounds[:-1])
            assert rounds[-1]["1"] != rounds[-1]["2"]


def test_sudden_death_happens():
    hits = [
        bool(
            swing_off.play({s: [_hitter(s)] for s in (1, 2)}, random.Random(n))[
                "sudden_death"
            ]
        )
        for n in range(100)
    ]
    assert any(hits) and not all(hits)


def test_winner_of_a_game_row():
    assert swing_off.winner({"score1": 5, "score2": 3, "swingoff": None}) == 1
    assert swing_off.winner({"score1": 2, "score2": 3}) == 2
    assert swing_off.winner({"score1": 3, "score2": 3, "swingoff": {"winner": 2}}) == 2
