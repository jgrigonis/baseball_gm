# tests/api/test_leaders_qualifiers.py
"""Who qualifies for the rate stat cards on the leaders tab and the flags on
the team stats table."""

from src.api.view_models.leaders import (
    defense_leaders,
    pitching_leaders,
    relief_leaders,
    rookie_leaders,
)
from src.api.view_models.team_stats import fielding_lines, stat_lines
from src.stats import qualifiers as q

GAMES = 100


def pit(pid, g, gs, outs, er, **extra):
    return {
        "player_id": pid, "first_name": pid, "last_name": "X",
        "city": "C", "mascot": "M", "team_id": "t",
        "pitch_games_played": g, "pitch_games_started": gs,
        "pitch_outs": outs, "pitch_earned_runs": er, "pitch_hits": 0,
        "pitch_walks": 0, "pitch_strike_outs": 0, "pitch_home_runs": 0,
        "pitch_wins": 0, "pitch_saves": 0, "pitch_holds": 0, **extra,
    }  # fmt: skip


def bat(pid, ab, hits, bb=0):
    return {
        "player_id": pid, "first_name": pid, "last_name": "X",
        "city": "C", "mascot": "M", "team_id": "t",
        "bat_ab": ab, "bat_hits": hits, "bat_walks": bb, "bat_doubles": 0,
        "bat_triples": 0, "bat_home_runs": 0, "bat_rbi": 0, "bat_runs": 0,
        "bat_strike_outs": 0, "bat_stolen_bases": 0, "bat_hbp": 0,
        "bat_sac_flys": 0, "bat_games_played": 10,
    }  # fmt: skip


def names(card):
    return [r["name"].split()[0] for r in card["rows"]]


def card(cats, label):
    return next(c for c in cats if c["label"] == label)


ROWS = [
    pit("starter", 30, 30, 330, 40),  # 110 IP, 3.27
    pit("closer", 60, 0, 180, 10, pitch_saves=30),  # 60 IP, 1.50
    pit("mopup", 20, 0, 90, 2),  # 30 IP: short even for a reliever
    pit("swing", 30, 15, 200, 5),  # half his games started: not a reliever
]


def test_ordinary_era_holds_relievers_to_an_inning_a_game():
    cats = pitching_leaders(ROWS, None, q.min_outs(GAMES))
    assert names(card(cats, "ERA")) == ["starter"]


def test_relief_era_takes_relievers_at_half_an_inning_a_game():
    cats = relief_leaders(ROWS, None, q.min_outs(GAMES, reliever=True))
    assert names(card(cats, "ERA")) == ["closer"]
    assert names(card(cats, "SV")) == ["closer"]


def test_rookie_cards_use_rookie_thresholds():
    bats = [bat("kid", 160, 60), bat("vet", 400, 150), bat("cup", 100, 50)]
    cats = rookie_leaders(bats, ROWS, None, {"kid", "cup", "closer"}, GAMES)
    # 155 PA to qualify: the kid makes it, the cup of coffee doesn't.
    assert names(card(cats, "AVG")) == ["kid"]
    # 50 IP for a rookie: the closer's 60 is enough.
    assert names(card(cats, "ERA")) == ["closer"]
    assert rookie_leaders(bats, ROWS, None, set(), GAMES) == []


def field(pid, pos, g, po, a, e):
    return {
        "player_id": pid, "name": pid, "city": "C", "mascot": "M",
        "team_id": "t", "position": pos, "g": g, "po": po, "a": a, "e": e,
        "pb": 0, "dp": 0, "tp": 0,
    }  # fmt: skip


def test_fielding_qualifiers_by_position():
    rows = [
        field("catch", "c", 50, 400, 30, 2),  # half the games: qualifies
        field("backup", "c", 20, 100, 10, 0),
        field("short", "ss", 66, 100, 200, 10),  # just short of 67
        field("regular", "ss", 67, 100, 200, 12),
        field("ace", "p", 30, 10, 20, 1),
        field("arm", "p", 40, 15, 35, 0),  # fewer innings, better in more chances
    ]
    outs = {"ace": 330, "arm": 200}
    cats = defense_leaders(rows, None, GAMES, outs)
    assert names(card(cats, "C FPCT")) == ["catch"]
    assert names(card(cats, "SS FPCT")) == ["regular"]
    assert names(card(cats, "P FPCT")) == ["arm", "ace"]


def test_team_stats_flags_relievers_and_fielders_on_their_own_marks():
    rows = [
        {**pit("closer", 60, 0, 180, 10), "pitch_losses": 0},
        {**pit("starter", 10, 10, 200, 20), "pitch_losses": 0},
        {**bat("walker", 280, 70, bb=40)},  # 320 PA, 280 AB
    ]
    batters, pitchers = stat_lines(rows, GAMES)
    flag = {p["player_id"]: p["qualified"] for p in pitchers}
    assert flag == {"closer": True, "starter": False}
    assert batters[0]["qualified"]  # PA, not AB, count

    fielders = fielding_lines(
        [
            {**field("catch", "c", 50, 400, 30, 2), "name": "catch"},
            {**field("ace", "p", 30, 10, 20, 1), "name": "ace"},
        ],
        GAMES,
        {"ace": 290},
    )
    assert [f["qualified"] for f in fielders] == [True, False]


def test_perfect_average_keeps_its_leading_one():
    from src.api.view_models.leaders import batting_leaders

    cats = batting_leaders([bat("Ace", 10, 10), bat("Joe", 10, 3)], None, 1)
    assert card(cats, "AVG")["rows"][0]["val"] == "1.000"
    assert card(cats, "AVG")["rows"][1]["val"] == ".300"
    assert card(cats, "OBP")["rows"][0]["val"] == "1.000"
