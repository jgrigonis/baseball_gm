# tests/stats/test_qualifiers.py
"""Rate stat qualifiers, per team game, after MLB's rules."""

from src.stats import qualifiers as q


def test_batting_needs_3_1_plate_appearances_a_game():
    assert q.min_pa(162) == 502
    assert q.min_pa(162, rookie=True) == 251


def test_plate_appearances_count_walks_hbp_and_sac_flies():
    row = {"bat_ab": 400, "bat_walks": 60, "bat_hbp": 5, "bat_sac_flys": 4}
    assert q.plate_appearances(row) == 469
    assert q.plate_appearances({}) == 0


def test_pitching_needs_an_inning_a_game_relievers_half():
    assert q.min_outs(162) == 486  # 162 IP
    assert q.min_outs(162, reliever=True) == 243  # 81 IP
    assert q.min_outs(162, rookie=True) == 243
    assert q.min_outs(60, reliever=True) == 90  # scales with the schedule


def test_a_reliever_started_fewer_than_half_his_games():
    assert q.is_reliever(60, 0)
    assert q.is_reliever(20, 9)
    assert not q.is_reliever(20, 10)
    assert not q.is_reliever(32, 32)
    assert not q.is_reliever(0, 0)


def test_fielding_needs_games_at_the_position():
    assert q.min_field_games("c", 162) == 81
    assert q.min_field_games("C", 162) == 81
    assert q.min_field_games("ss", 162) == 108
    assert q.min_field_outs(162) == 486


def _p(pid, outs, fpct, chances):
    return {"id": pid, "outs": outs, "fpct": fpct, "chances": chances}


def test_pitcher_fpct_lets_in_a_short_pitcher_with_more_chances():
    pool = q.pitcher_fpct_pool(
        [
            _p("ace", 600, 0.970, 33),  # qualified leader
            _p("short", 300, 0.980, 50),  # better, in more chances: in
            _p("few", 300, 1.000, 10),  # better, but fewer chances: out
            _p("worse", 300, 0.950, 60),  # more chances, worse FPCT: out
        ],
        162,
    )
    assert {p["id"] for p in pool} == {"ace", "short"}


def test_pitcher_fpct_pool_is_empty_with_no_one_qualified():
    assert q.pitcher_fpct_pool([_p("a", 30, 1.0, 5)], 162) == []
