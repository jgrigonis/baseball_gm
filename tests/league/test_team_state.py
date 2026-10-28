# tests/league/test_team_state.py
"""Team states from their inputs, and how sticky they are
(src/league/team_state.py)."""

import pytest

from src.league.team_state import (
    MIN_CHECKPOINTS,
    STATES,
    Inputs,
    Previous,
    classify,
    describe,
    settle,
)


def inputs(**kw):
    base = dict(
        teams=12,
        rank_now=0.5,
        rank_future=0.5,
        core_age=28.0,
        league_core_age=28.0,
        old_share=0.1,
        farm_rank=0.5,
    )
    return Inputs(**(base | kw))


@pytest.mark.parametrize(
    "kw, state",
    [
        # Top tier now.
        (dict(rank_now=0.0, rank_future=0.1), "contending"),
        (dict(rank_now=0.0, rank_future=0.1, core_age=29.5), "all-in"),
        (dict(rank_now=0.1, rank_future=0.8), "all-in"),
        # Middle.
        (dict(rank_now=0.5, rank_future=0.5), "retooling"),
        (dict(rank_now=0.5, rank_future=0.2), "ramping-up"),
        (dict(rank_now=0.4, rank_future=0.9, old_share=0.3), "aging-out"),
        # Bottom.
        (dict(rank_now=0.9, rank_future=0.9), "rebuilding"),
        (dict(rank_now=0.9, rank_future=0.2), "ramping-up"),
        (
            dict(rank_now=0.9, rank_future=0.7, core_age=26.5, farm_rank=0.1),
            "ramping-up",
        ),
        (dict(rank_now=0.9, rank_future=0.9, core_age=31.0), "rebuilding"),
    ],
)
def test_classify(kw, state):
    assert classify(inputs(**kw)) == state


def test_every_state_has_words():
    assert all(describe(s) for s in STATES)


def test_standings_decide_now_once_enough_games_are_played():
    weak_roster = dict(rank_now=0.9, rank_future=0.9)
    # Early on, the roster says rebuilding even in a playoff spot.
    assert classify(inputs(**weak_roster, played=10, games_back=0.0)) == "rebuilding"
    # Later, a team in the race contends whatever the ratings say...
    assert classify(inputs(**weak_roster, played=40, games_back=3.0)) == "all-in"
    # ...and a strong roster 12 games back is out of it: with its future
    # still bright, it builds toward next year rather than tearing down.
    strong = inputs(rank_now=0.0, rank_future=0.0, played=40, games_back=12.0)
    assert strong.tier_now == "bottom"
    assert classify(strong) == "ramping-up"


def previous(state, held, candidate=None, tier="middle"):
    return Previous(state, held, candidate or state, tier)


def test_a_first_state_is_whatever_the_inputs_say():
    assert settle(None, inputs(rank_now=0.9, rank_future=0.9)) == ("rebuilding", 1)


def test_a_state_holds_for_a_while():
    middling = inputs()  # retooling
    prev = previous("contending", held=1, candidate="retooling", tier="top")
    assert settle(prev, middling) == ("contending", 2)


def test_moving_out_takes_the_same_answer_twice_after_the_minimum():
    middling = inputs()
    once = previous("contending", MIN_CHECKPOINTS, candidate="contending", tier="top")
    assert settle(once, middling) == ("contending", MIN_CHECKPOINTS + 1)
    twice = previous("contending", MIN_CHECKPOINTS, candidate="retooling", tier="top")
    assert settle(twice, middling) == ("retooling", 1)


def test_a_collapse_changes_it_at_once():
    collapsed = inputs(rank_now=0.0, rank_future=0.9, played=60, games_back=15.0)
    prev = previous("contending", held=1, tier="top")
    assert settle(prev, collapsed) == ("rebuilding", 1)


def test_staying_put_counts_up():
    assert settle(previous("retooling", 2), inputs()) == ("retooling", 3)


def test_a_win_now_gm_counts_as_top_tier_further_down():
    # Just outside the top third by rank.
    i = dict(rank_now=0.38, rank_future=0.4)
    assert inputs(**i).tier_now == "middle"
    assert inputs(**i, lean=1.0).tier_now == "top"
    assert inputs(**i, lean=-1.0).tier_now == "middle"


def test_a_patient_gm_sees_the_bottom_sooner():
    i = dict(rank_now=0.62, rank_future=0.62)
    assert classify(inputs(**i)) == "retooling"
    assert classify(inputs(**i, lean=-1.0)) == "rebuilding"
    assert classify(inputs(**i, lean=1.0)) == "retooling"


def test_lean_moves_the_games_back_lines_too():
    race = dict(played=40, rank_now=0.5, rank_future=0.5)
    assert inputs(**race, games_back=7.0).tier_now == "middle"
    assert inputs(**race, games_back=7.0, lean=1.0).tier_now == "top"
    assert inputs(**race, games_back=8.0, lean=-1.0).tier_now == "bottom"
