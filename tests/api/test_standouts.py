"""Standout performances in one game (src/api/view_models/standouts.py)."""

from src.api.view_models.line_score import headline
from src.api.view_models.standouts import standouts


def _bat(team, last, H=1, AB=4, doubles=0, triples=0, HR=0, RBI=0, R=0):
    return {
        "team_id": team,
        "player_id": last.lower(),
        "first_name": "J",
        "last_name": last,
        "AB": AB,
        "H": H,
        "doubles": doubles,
        "triples": triples,
        "HR": HR,
        "RBI": RBI,
        "R": R,
    }


def _pit(team, last, outs=27, H=0, R=0, BB=0, K=5, HBP=0, NH=0, SHO=0):
    return {
        "team_id": team,
        "player_id": last.lower(),
        "first_name": "J",
        "last_name": last,
        "outs": outs,
        "H": H,
        "R": R,
        "BB": BB,
        "K": K,
        "HBP": HBP,
        "NH": NH,
        "SHO": SHO,
    }


def _game(away_score, home_score):
    return {
        "away_team_id": "a",
        "home_team_id": "h",
        "away_city": "Omaha",
        "away_mascot": "Steaks",
        "home_city": "Toronto",
        "home_mascot": "Sentinels",
        "away_score": away_score,
        "home_score": home_score,
        "innings_played": 9,
        "line_score": None,
    }


def test_ordinary_lines_are_not_standouts():
    bats = [_bat("h", "Leek", H=3, HR=1, RBI=4), _bat("a", "Graves", H=2)]
    pits = [_pit("h", "Allen", outs=21, R=1, H=5, K=9)]

    assert standouts(bats, pits) == []


def test_cycle_needs_a_single_double_triple_and_homer():
    cycle = _bat("a", "Graves", H=4, AB=5, doubles=1, triples=1, HR=1, RBI=3, R=2)
    no_single = _bat("h", "Leek", H=3, doubles=1, triples=1, HR=1)

    (st,) = standouts([cycle, no_single], [])

    assert st["label"] == "Cycle"
    assert st["feats"] == ["Cycle", "4 hits"]
    assert st["line"] == "4-for-5, 2B, 3B, HR, 3 RBI, 2 R"


def test_ranked_by_rarity_and_capped_at_three():
    bats = [
        _bat("h", "Bright", H=4, AB=5),
        _bat("h", "Leek", H=2, HR=2, RBI=2),
        _bat("a", "Graves", H=3, HR=3, RBI=5),
        _bat("a", "Moss", H=2, RBI=6),
    ]
    pits = [_pit("h", "Allen", outs=24, H=7, R=4, K=12)]

    labels = [s["label"] for s in standouts(bats, pits)]

    assert labels == ["3 HR", "6 RBI", "2 HR"]
    assert len(standouts(bats, pits, limit=None)) == 5


def test_perfect_game_no_hitter_shutout_and_scoreless_innings():
    perfect = _pit("h", "Allen", NH=1, SHO=1, K=8)
    walked_one = _pit("h", "Allen", NH=1, SHO=1, BB=1)
    shutout = _pit("h", "Allen", H=4, SHO=1, K=11)
    eight = _pit("h", "Allen", outs=25, H=3)

    assert standouts([], [perfect])[0]["label"] == "Perfect game"
    assert standouts([], [perfect], errors={"h": 1})[0]["label"] == "No-hitter"
    assert standouts([], [walked_one])[0]["label"] == "No-hitter"
    assert standouts([], [shutout])[0]["feats"] == ["Shutout", "11 K"]
    assert standouts([], [eight])[0]["label"] == "8.1 scoreless IP"


def test_perfect_game_headline_comes_first():
    pits = [_pit("h", "Allen", NH=1, SHO=1)]
    nh = [{"pitchers": "J. Allen", "combined": False, "team": "Toronto Sentinels"}]

    assert (
        headline(_game(0, 2), [], pits, nh)
        == "Allen throws a perfect game against the Steaks"
    )


def test_headline_for_cycle_and_rbi():
    cycle = _bat("h", "Leek", H=4, AB=4, doubles=1, triples=1, HR=1)
    assert (
        headline(_game(3, 5), [cycle], [], [])
        == "Leek hits for the cycle as the Sentinels beat the Steaks, 5-3"
    )
    rbi = _bat("h", "Moss", H=2, RBI=5)
    assert (
        headline(_game(3, 5), [rbi], [], [])
        == "Moss drives in 5 as the Sentinels beat the Steaks, 5-3"
    )


def test_loser_makes_the_headline_only_for_a_rare_feat():
    four_hits = [_bat("a", "Graves", H=4)]
    assert headline(_game(3, 5), four_hits, [], []) == "Sentinels beat the Steaks, 5-3"

    three_hr = [_bat("a", "Graves", H=3, HR=3, RBI=3)]
    assert (
        headline(_game(3, 5), three_hr, [], [])
        == "Graves's three homers not enough as the Sentinels beat the Steaks, 5-3"
    )
