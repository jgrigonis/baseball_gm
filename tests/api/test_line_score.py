"""The game panel's scoreboard rows and headline (src/api/view_models/line_score.py)."""

from src.api.view_models.line_score import headline, line_score


def _game(away, home, **kw):
    g = {
        "away_team_id": "a",
        "home_team_id": "h",
        "away_city": "Omaha",
        "away_mascot": "Steaks",
        "home_city": "Toronto",
        "home_mascot": "Sentinels",
        "away_score": sum(away or []),
        "home_score": sum(home or []),
        "innings_played": 9,
        "line_score": {"away": away, "home": home} if away is not None else None,
    }
    g["winner_id"] = "h" if g["home_score"] > g["away_score"] else "a"
    g.update(kw)
    return g


def _bat(team, last, H=1, HR=0, AB=4):
    return {"team_id": team, "last_name": last, "H": H, "HR": HR, "AB": AB}


def _pit(team, last, K=3):
    return {"team_id": team, "last_name": last, "K": K}


def test_rows_pad_short_innings_and_carry_rhe():
    g = _game([0, 1], [2])
    sb = line_score(g, hits={"a": 5, "h": 7}, errors={"a": 1})

    assert sb["innings"] == list(range(1, 10))
    away, home = sb["rows"]
    assert away["cells"] == ["0", "1"] + ["0"] * 7
    assert (away["R"], away["H"], away["E"], away["won"]) == (1, 5, 1, False)
    assert (home["R"], home["H"], home["E"], home["won"]) == (2, 7, 0, True)
    assert home["code"] == "TOR"


def test_home_team_that_did_not_bat_in_the_ninth_gets_an_x():
    g = _game([0] * 9, [1] + [0] * 8)

    home = line_score(g, {}, {})["rows"][1]

    assert home["cells"][-1] == "X"


def test_walk_off_keeps_the_last_bottom_half():
    g = _game([1] + [0] * 9, [0] * 9 + [2], innings_played=10)

    sb = line_score(g, {}, {})

    assert sb["innings"][-1] == 10
    assert sb["rows"][1]["cells"][-1] == "2"
    assert headline(g, [], [], []) == "Sentinels walk it off in the 10th, 2-1"


def test_game_without_a_saved_line_score_shows_only_rhe():
    g = _game(None, None, away_score=3, home_score=4, winner_id="h")

    sb = line_score(g, {"h": 8}, {})

    assert sb["innings"] == []
    assert sb["rows"][1]["cells"] == []
    assert sb["rows"][1]["R"] == 4


def test_no_hitter_comes_first():
    g = _game([0] * 9, [1] + [0] * 8)
    nh = [{"pitchers": "J. Allen", "combined": False, "team": "Toronto Sentinels"}]

    assert headline(g, [], [], nh) == "Allen no-hits the Steaks"


def test_comeback():
    g = _game([4, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 3, 2, 0])

    assert (
        headline(g, [], [], [])
        == "Sentinels rally from four down to beat the Steaks, 5-4"
    )


def test_complete_game_shutout():
    g = _game([0] * 9, [2] + [0] * 8)

    assert (
        headline(g, [], [_pit("h", "Allen")], [])
        == "Allen blanks the Steaks on a complete game, 2-0"
    )


def test_big_day_from_a_winning_hitter():
    g = _game([1] + [0] * 8, [0, 3] + [0] * 7)
    bats = [_bat("h", "Leek", H=2, HR=2), _bat("a", "Graves", H=4, HR=3)]

    assert (
        headline(g, bats, [], [])
        == "Leek's two homers power the Sentinels past the Steaks, 3-1"
    )


def test_strikeouts_then_four_hits():
    g = _game([1] + [0] * 8, [0, 3] + [0] * 7)

    assert (
        headline(g, [], [_pit("h", "Allen", K=11)], [])
        == "Allen fans 11 as the Sentinels top the Steaks, 3-1"
    )
    assert (
        headline(g, [_bat("h", "Bright", H=4, AB=5)], [], [])
        == "Bright goes 4-for-5 as the Sentinels beat the Steaks, 3-1"
    )


def test_plain_results():
    assert (
        headline(_game([9] + [0] * 8, [1] + [0] * 8), [], [], [])
        == "Steaks rout the Sentinels, 9-1"
    )
    assert (
        headline(_game([2] + [0] * 8, [1] + [0] * 8), [], [], [])
        == "Steaks edge the Sentinels, 2-1"
    )
    assert (
        headline(_game([4] + [0] * 8, [1] + [0] * 8), [], [], [])
        == "Steaks beat the Sentinels, 4-1"
    )
    g = _game([0] * 10 + [2], [1] + [0] * 9 + [0], innings_played=11)
    # The Steaks won in the 11th after trailing 1-0: not a three-run comeback
    assert headline(g, [], [], []) == "Steaks outlast the Sentinels in 11, 2-1"
