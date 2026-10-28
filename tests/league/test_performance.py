# tests/league/test_performance.py
"""Form: how a player's season stats compare to his ratings, in rating
points, regressed by how much he's played."""

import pytest

from src.league import performance as perf


def _bat(pa, woba):
    """Totals for a hitter with this many walks-and-singles PAs at this
    wOBA (all singles and outs)."""
    singles = round(woba * pa / 0.89)
    return {
        "bat_ab": pa,
        "bat_hits": singles,
        "bat_doubles": 0,
        "bat_triples": 0,
        "bat_home_runs": 0,
        "bat_walks": 0,
        "bat_hbp": 0,
        "bat_sac_flys": 0,
    }


def _pitch(outs, k, bb, hr, starts=10, games=10):
    return {
        "pitch_outs": outs,
        "pitch_strike_outs": k,
        "pitch_walks": bb,
        "pitch_hit_batters": 0,
        "pitch_home_runs": hr,
        "pitch_games_started": starts,
        "pitch_games_played": games,
    }


def test_woba():
    t = {
        "bat_ab": 8,
        "bat_hits": 4,
        "bat_doubles": 1,
        "bat_triples": 1,
        "bat_home_runs": 1,
        "bat_walks": 1,
        "bat_hbp": 1,
        "bat_sac_flys": 0,
    }
    value, pa = perf.woba(t)
    assert pa == 10
    assert value == pytest.approx((0.69 + 0.72 + 0.89 + 1.27 + 1.62 + 2.10) / 10)


def test_hitting_to_his_rating_is_no_form():
    offense = 65
    expected = perf.WOBA_BASE + perf.WOBA_PER_POINT * offense
    t = _bat(600, expected)
    assert abs(perf.hitter_form(offense, t)) < 0.5


def test_hitter_form_is_regressed_by_playing_time():
    offense = 60
    hot = perf.WOBA_BASE + perf.WOBA_PER_POINT * (offense + 10)
    short = perf.hitter_form(offense, _bat(30, hot))
    full = perf.hitter_form(offense, _bat(600, hot))
    assert 0 < short < 1.5  # a couple of hot weeks barely count
    assert 5 < full < 8  # a full season counts about two thirds


def test_form_is_capped():
    assert perf.hitter_form(40, _bat(5000, 0.600)) == perf.MAX_FORM
    assert perf.hitter_form(90, _bat(5000, 0.0)) == -perf.MAX_FORM


def test_no_stats_no_form():
    assert perf.hitter_form(60, _bat(0, 0)) == 0.0
    assert perf.pitcher_form(60, 60, _pitch(0, 0, 0, 0)) == 0.0
    assert perf.form({"overall_offense": 60, "sp": 60, "rp": 60}, None) == (0.0, 0.0)


def test_pitcher_form_judges_starters_and_relievers_on_their_own_line():
    # 100 innings, lots of strikeouts: better than his rating says.
    ace = _pitch(300, k=130, bb=20, hr=5)
    assert perf.pitcher_form(60, 40, ace) > 0
    # The same line out of the pen, against a reliever's expected FIP.
    pen = _pitch(300, k=130, bb=20, hr=5, starts=0, games=60)
    assert perf.pitcher_form(40, 60, pen) > 0
    # Walks and homers: worse.
    wild = _pitch(300, k=40, bb=70, hr=25)
    assert perf.pitcher_form(70, 40, wild) < 0
