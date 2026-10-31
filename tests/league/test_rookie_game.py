# tests/league/test_rookie_game.py
"""The Rookie Game's rules (src/league/rookie_game.py): who's in it and who
runs it."""

from src.league import rookie_game
from src.league.all_star import FIELD_SLOTS, Window


def _cand(pid, slot, team="t1", z=0.0):
    return {
        "player_id": pid,
        "team_id": team,
        "slot": slot,
        "z": {"bat": z, "trad": z, "talent": z},
    }


def _league(per_slot=3, pitchers=20):
    cands = []
    for slot in FIELD_SLOTS + ("dh",):
        for i in range(per_slot):
            cands.append(_cand(f"{slot}{i}", slot, z=-i))
    for i in range(pitchers):
        cands.append(_cand(f"p{i}", "p", z=-i))
    return cands


def test_the_pool_is_the_best_rookies_who_are_not_all_stars():
    cands = _league()
    rookies = {c["player_id"] for c in cands} - {"c0"}
    rows = rookie_game.pool(cands, rookies, left_out={"ss0"})
    ids = {r["player_id"] for r in rows}
    assert len(rows) == rookie_game.POOL_SIZE
    assert "c0" not in ids and "ss0" not in ids  # not a rookie, an All-Star
    assert {"ss1", "ss2", "c1", "c2"} <= ids
    assert sum(1 for r in rows if r["slot"] == "p") >= rookie_game.QUOTA["p"]
    assert all(r["points"] == 0 for r in rows)


def test_too_few_rookies_means_no_game():
    cands = _league(per_slot=1, pitchers=20)
    ids = {c["player_id"] for c in cands}
    assert rookie_game.pool(cands, ids, set()) == []  # 9 hitters
    cands = _league(per_slot=3, pitchers=3)
    ids = {c["player_id"] for c in cands}
    assert rookie_game.pool(cands, ids, set()) == []  # 3 pitchers
    assert rookie_game.pool(_league(), set(), set()) == []


def test_the_captains_have_the_most_rookies_but_not_the_all_star_game():
    rows = [{"team_id": t} for t in ["a"] * 5 + ["b"] * 4 + ["c"] * 2 + ["d"] * 2]
    standings = ["a", "b", "d", "c", "e"]
    assert rookie_game.captains(rows, standings, ["a", "e"]) == ["b", "d"]
    # Ties go to the better record.
    assert rookie_game.captains(rows, standings, ["a", "b"]) == ["d", "c"]
    # Not enough other teams with rookies: back to everyone.
    assert rookie_game.captains(rows, standings, ["b", "c", "d"]) == ["a", "b"]
    assert rookie_game.captains(rows, ["a"], []) == []


def test_the_game_is_on_the_first_day_of_the_break():
    w = Window("2025-06-21", "2025-07-04", "2025-07-09")
    assert rookie_game.game_date(w) == "2025-07-05"
