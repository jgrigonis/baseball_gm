# tests/league/test_all_star.py
"""All-Star voting rules (src/league/all_star.py): the voting window, who's on
the ballot at which position, how GMs' dials and loyalty change a ballot, and
how the votes become the 64-player pool."""

import random

from src.league import all_star
from src.league.all_star import BALLOT, FIELD_SLOTS, POOL_SIZE, QUOTA, SLOTS

_ZERO_STATS = {
    k: 0
    for k in (
        "bat_games_played bat_ab bat_hits bat_doubles bat_triples bat_home_runs "
        "bat_rbi bat_walks bat_hbp bat_sac_flys bat_stolen_bases pitch_games_played "
        "pitch_games_started pitch_wins pitch_saves pitch_outs pitch_earned_runs "
        "pitch_home_runs pitch_walks pitch_hit_batters pitch_strike_outs"
    ).split()
}


def _cand(pid, slot, team="t1", quality=0.0, **kw):
    """A candidate already on the ballot, with z-scores set by hand."""
    c = {
        **_ZERO_STATS,
        "player_id": pid,
        "name": pid,
        "team_id": team,
        "slot": slot,
        "z": {"bat": quality, "trad": quality, "talent": quality, "glove": 0},
    }
    c.update(kw)
    return c


def _league(per_slot=10):
    """per_slot candidates at every slot, p0 the best at each."""
    cands = []
    for slot in SLOTS:
        n = per_slot * (3 if slot == "p" else 1)
        for i in range(n):
            cands.append(_cand(f"{slot}{i}", slot, team=f"t{i % 5}", quality=-i))
    return cands


# ── The window ───────────────────────────────────────────────────────────────


def _days(start, n):
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    return [(d + timedelta(days=i)).isoformat() for i in range(n)]


def test_the_window_closes_before_the_one_gap_in_the_calendar():
    dates = _days("2025-04-01", 100) + _days("2025-07-14", 60)
    w = all_star.window(dates)
    assert w.closes == "2025-07-09"
    assert w.resumes == "2025-07-14"
    assert w.opens == "2025-06-26"  # 14 days of games, the closing day included


def test_a_season_with_no_break_has_no_window():
    assert all_star.window(_days("2025-04-01", 170)) is None
    assert all_star.window([]) is None


# ── The ballot ───────────────────────────────────────────────────────────────


def _player(pid, pos, starts, pitched=0, outs=0, **ratings):
    return {
        **_ZERO_STATS,
        "player_id": pid,
        "start_position": pos,
        "starts": starts,
        "pitch_games_played": pitched,
        "pitch_outs": outs,
        "ratings": {"ss": 70, "cf": 60, **ratings},
    }


def test_players_go_on_the_ballot_where_they_have_started_most():
    players = [
        _player("short", "ss", 80),
        _player("dh", "dh", 80),
        _player("ace", None, 0, pitched=20, outs=360),
        # a pitcher who batted for himself now and then is still a pitcher
        _player("two_way", "dh", 5, pitched=30, outs=150),
        _player("bench", "cf", 10),  # too few starts
        _player("mopup", None, 0, pitched=10, outs=40),  # too few outs
    ]
    on = {c["player_id"]: c for c in all_star.on_ballot(players, games=96)}
    assert set(on) == {"short", "dh", "ace", "two_way"}
    assert on["short"]["slot"] == "ss" and on["short"]["glove"] == 70
    assert on["dh"]["slot"] == "dh" and on["dh"]["glove"] == 0
    assert on["ace"]["slot"] == "p" and on["two_way"]["slot"] == "p"


def test_a_neutral_ballot_has_the_best_at_each_slot():
    b = all_star.ballot(_league())
    assert {s: len(b[s]) for s in SLOTS} == BALLOT
    assert b["ss"] == ["ss0", "ss1"]
    assert b["p"] == [f"p{i}" for i in range(9)]


def test_a_loyal_gm_votes_for_his_own_players():
    cands = _league()
    neutral = all_star.ballot(cands)
    homer = all_star.ballot(cands, {"loyalty": 100}, team_id="t4")
    mine = {c["player_id"] for c in cands if c["team_id"] == "t4"}
    count = lambda b: sum(pid in mine for picks in b.values() for pid in picks)  # noqa: E731
    assert count(homer) > count(neutral)


def test_dials_change_what_a_gm_values():
    slugger = _cand(
        "slugger", "ss", z={"bat": 2.0, "trad": 2.0, "talent": 0, "glove": -2}
    )
    glove = _cand("glove", "ss", z={"bat": 0, "trad": 0, "talent": 0, "glove": 2.0})
    bat_first = {"offense_defense": 100}
    glove_first = {"offense_defense": 0}
    assert all_star.score(slugger, bat_first) > all_star.score(glove, bat_first)
    gap_bat = all_star.score(slugger, bat_first) - all_star.score(glove, bat_first)
    gap_glove = all_star.score(slugger, glove_first) - all_star.score(
        glove, glove_first
    )
    assert gap_glove < gap_bat

    modern = _cand("modern", "p", z={"bat": 2.0, "trad": -1.0, "talent": 0})
    old = _cand("old", "p", z={"bat": -1.0, "trad": 2.0, "talent": 0})
    assert all_star.score(modern, {"analytics": 100}) > all_star.score(
        old, {"analytics": 100}
    )
    assert all_star.score(old, {"analytics": 0}) > all_star.score(
        modern, {"analytics": 0}
    )


def test_ai_ballots_wobble():
    cands = _league()
    rng = random.Random(1)
    ballots = [all_star.ballot(cands, {}, "t0", rng) for _ in range(20)]
    assert len({tuple(b["p"]) for b in ballots}) > 1


def test_a_sent_ballot_keeps_only_valid_picks():
    cands = _league()
    raw = {
        "ss": ["ss3", "ss3"],  # twice
        "c": ["cf0", "c1"],  # not a catcher
        "p": ["p1", None, "p2"] + ["p9"] * 9,  # a blank, too many picks
        "dh": ["nobody"],
    }
    b = all_star.clean_ballot(raw, cands)
    assert b["ss"] == ["ss3", None]
    assert b["c"] == [None, "c1"]
    assert b["p"] == ["p1", None, "p2", "p9", None, None, None, None, None]
    assert b["dh"] == [None]
    assert b["1b"] == []


def test_points():
    b = {"ss": ["a", "b"], "dh": ["c"], "p": ["d", None, "e"]}
    assert all_star.tally([b, b]) == {"a": 4, "b": 2, "c": 2, "d": 2, "e": 2}


# ── The pool ─────────────────────────────────────────────────────────────────


def test_the_pool_fills_every_quota_and_the_wildcards():
    cands = _league()
    pool = all_star.select_pool(cands, all_star.tally([all_star.ballot(cands)]))
    assert len(pool) == POOL_SIZE
    regular = [r for r in pool if not r["wildcard"]]
    for slot in SLOTS:
        assert sum(r["slot"] == slot for r in regular) == QUOTA[slot]
    assert sum(r["wildcard"] for r in pool) == POOL_SIZE - sum(QUOTA.values())


def test_players_nobody_voted_for_fill_in_by_stats():
    cands = _league()
    pool = all_star.select_pool(cands, {})
    ss = [r["player_id"] for r in pool if r["slot"] == "ss" and not r["wildcard"]]
    assert ss == ["ss0", "ss1", "ss2", "ss3"]


def test_the_most_votes_beat_the_best_stats():
    cands = _league()
    pts = {"ss9": 10}
    pool = all_star.select_pool(cands, pts)
    ss = [r["player_id"] for r in pool if r["slot"] == "ss" and not r["wildcard"]]
    assert ss[0] == "ss9"


def test_a_tie_at_the_cut_line_takes_a_wildcard_spot():
    cands = _league()
    # Five shortstops tied for the four spots.
    pts = {f"ss{i}": 3 for i in range(5)}
    pool = all_star.select_pool(cands, pts)
    ids = {r["player_id"]: r for r in pool}
    assert all(f"ss{i}" in ids for i in range(5))
    assert ids["ss4"]["wildcard"]
    assert len(pool) == POOL_SIZE


def test_wildcards_go_to_the_most_points_at_any_position():
    cands = _league()
    # cf0-3 and p0-17 fill their quotas; cf7 and p25 are next.
    pts = {**{f"cf{i}": 9 for i in range(4)}, **{f"p{i}": 6 for i in range(18)}}
    pts.update(cf7=5, p25=4)
    pool = all_star.select_pool(cands, pts)
    wild = [r["player_id"] for r in pool if r["wildcard"]]
    assert wild[:2] == ["cf7", "p25"]


def test_a_small_league_uses_whoever_it_has():
    cands = [_cand(f"{s}0", s) for s in FIELD_SLOTS]
    pool = all_star.select_pool(cands, {})
    assert len(pool) == len(FIELD_SLOTS)


def test_a_tie_for_the_last_wildcard_spot_is_found():
    cands = _league(per_slot=20)
    # The catchers' 4 spots, 11 clear wildcards, then two tied for the last.
    pts = {f"c{i}": 20 for i in range(4)}
    pts.update({f"c{i}": 9 for i in range(4, 15)})
    pts.update(c15=2, c16=2)
    pool = all_star.select_pool(cands, pts)
    assert pool[-1]["player_id"] == "c15"  # the better stats
    assert all_star.last_spot_tie(cands, pts, pool) == ["c15", "c16"]


def test_no_tie_for_the_last_spot_without_points():
    cands = _league(per_slot=20)
    pool = all_star.select_pool(cands, {})
    assert all_star.last_spot_tie(cands, {}, pool) == []
    pts = {f"c{i}": 20 for i in range(4)}
    pts.update({f"c{i}": 9 for i in range(4, 16)})
    pool = all_star.select_pool(cands, pts)
    assert all_star.last_spot_tie(cands, pts, pool) == []


# ── The captains' draft ──────────────────────────────────────────────────────


def test_the_draft_snakes():
    order = [all_star.side_to_pick(n) for n in range(1, 9)]
    assert order == [1, 2, 2, 1, 1, 2, 2, 1]


def _row(pid, slot, points=0, score=0.0):
    return {"player_id": pid, "slot": slot, "points": points, "score": score}


def test_an_ai_captain_takes_the_most_votes():
    left = [_row("a", "ss", 3), _row("b", "c", 5), _row("c", "c", 5, 1.0)]
    assert all_star.ai_pick(left, [])["player_id"] == "c"


def test_an_ai_captain_fills_his_needs_first():
    mine = [_row("x", "c"), _row("y", "c")]
    left = [_row("a", "ss", 3), _row("b", "c", 9)]
    assert all_star.ai_pick(left, mine)["player_id"] == "a"
    # Needs met, or nobody left at them: the best left anywhere.
    assert all_star.ai_pick([_row("b", "c", 9)], mine)["player_id"] == "b"
    assert all_star.ai_pick([], mine) is None


# ── The game ─────────────────────────────────────────────────────────────────


def test_the_game_is_on_the_third_day_of_the_break():
    w = all_star.Window("2025-06-01", "2025-06-14", "2025-06-19")
    assert all_star.game_date(w) == "2025-06-17"
    short = all_star.Window("2025-06-01", "2025-06-14", "2025-06-17")
    assert all_star.game_date(short) == "2025-06-16"


def _line(pid, side, **kw):
    line = {
        k: 0
        for k in (
            "bat_ab bat_runs bat_hits bat_doubles bat_triples bat_home_runs "
            "bat_rbi bat_walks bat_strike_outs bat_stolen_bases pitch_outs "
            "pitch_hits pitch_runs pitch_earned_runs pitch_walks "
            "pitch_strike_outs pitch_home_runs"
        ).split()
    }
    line.update(player_id=pid, side=side, batting_order=None, pitch_order=None)
    line.update(kw)
    return line


def test_the_mvp_is_the_winners_best():
    lines = [
        _line(
            "slugger",
            1,
            batting_order=3,
            bat_ab=4,
            bat_hits=2,
            bat_home_runs=2,
            bat_rbi=4,
            bat_runs=2,
        ),
        _line("ace", 1, pitch_order=1, pitch_outs=4, pitch_strike_outs=4),
        _line(
            "loser",
            2,
            batting_order=1,
            bat_ab=4,
            bat_hits=4,
            bat_home_runs=4,
            bat_rbi=4,
            bat_runs=4,
        ),
    ]
    assert all_star.mvp(lines, 1) == "slugger"
    assert all_star.mvp(lines, 2) == "loser"
    assert all_star.mvp([], 1) is None


def test_a_line_in_a_few_words():
    bat = _line(
        "a", 1, batting_order=1, bat_ab=4, bat_hits=2, bat_home_runs=1, bat_rbi=3
    )
    assert all_star.line_text(bat) == "2-4, HR, 3 RBI"
    arm = _line("b", 1, pitch_order=2, pitch_outs=4, pitch_strike_outs=3)
    assert all_star.line_text(arm) == "1.1 IP, 3 K"
