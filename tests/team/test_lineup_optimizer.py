# tests/team/test_lineup_optimizer.py
"""
Testing Philosophy for LineupOptimizer

We test contracts and invariants, not baseball opinions.

We verify that it:

✅ Selects pitchers deterministically
✅ Produces correct lineup sizes
✅ Preserves batting order
✅ Assigns valid positions
✅ Respects DH rules
✅ Never mutates players
✅ Fails loudly on invalid inputs

We do not test:
Exact batting orders beyond simple dominance cases
Relative baseball “correctness”
PlayerEvaluator logic
"""

# tests/conftest.py (or inline)

from unittest.mock import MagicMock
from src.player.player_in_game import PlayerInGame
from types import SimpleNamespace


def make_player(id, ratings):
    p = MagicMock(spec=PlayerInGame)

    # record is a runtime attribute → must be mocked explicitly
    p.record = SimpleNamespace(id=id)

    p.ratings = ratings
    return p


def test_select_pitcher_uses_p_rating_then_id():
    """select_pitcher chooses highest pitcher rating"""
    from src.team.lineup_optimizer import LineupOptimizer

    p1 = make_player("a", {"p": 80})
    p2 = make_player("b", {"p": 90})
    p3 = make_player("c", {"p": 90})  # tie → higher id wins

    pitcher = LineupOptimizer.select_pitcher([p1, p2, p3])

    assert pitcher is p3


def test_optimize_returns_lineup_and_pitcher():
    from src.team.lineup_optimizer import LineupOptimizer

    players = [make_player(str(i), {"p": i}) for i in range(10)]

    lineup, pitcher = LineupOptimizer.optimize(players)

    assert pitcher in players
    assert isinstance(lineup, list)


def test_optimize_respects_dh_rule():
    from src.team.lineup_optimizer import LineupOptimizer

    players = [make_player(str(i), {}) for i in range(10)]

    lineup_dh, _ = LineupOptimizer.optimize(players, dh=True)
    lineup_no_dh, _ = LineupOptimizer.optimize(players, dh=False)

    assert len(lineup_dh) == 9
    assert len(lineup_no_dh) == 8


def test_build_lineup_preserves_order():
    from src.team.lineup_optimizer import LineupOptimizer

    p1, p2, p3 = (
        make_player("1", {}),
        make_player("2", {}),
        make_player("3", {}),
    )

    assignments = {p1: "cf", p2: "ss", p3: "2b"}

    lineup = LineupOptimizer.build_lineup([p1, p2, p3], assignments)

    assert [slot.player for slot in lineup] == [p1, p2, p3]


import pytest


def test_offensive_batting_order_requires_minimum_hitters():
    from src.team.lineup_optimizer import LineupOptimizer

    hitters = [make_player(str(i), {}) for i in range(5)]

    with pytest.raises(ValueError):
        LineupOptimizer.offensive_batting_order(hitters, dh=True)


from src.team.lineup_slot import LINEUP_SLOTS


def test_assign_positions_priority_uses_valid_positions():
    from src.team.lineup_optimizer import LineupOptimizer

    players = [make_player(str(i), {"ss": i}) for i in range(8)]

    assignments = LineupOptimizer.assign_positions_priority(players, dh=True)

    for pos in assignments.values():
        assert pos in LINEUP_SLOTS or pos == "dh"


def test_assign_positions_greedy_assigns_all_players():
    from src.team.lineup_optimizer import LineupOptimizer

    players = [make_player(str(i), {"cf": i}) for i in range(9)]

    assignments = LineupOptimizer.assign_positions_greedy(players, dh=True)

    assert set(assignments.keys()) == set(players)


from unittest.mock import patch


def test_optimizer_does_not_mutate_players():
    from src.team.lineup_optimizer import LineupOptimizer

    p = make_player("1", {"p": 10})
    original_ratings = dict(p.ratings)

    with (
        patch.object(LineupOptimizer, "prioritized_lineup", return_value=[]),
        patch.object(LineupOptimizer, "select_pitcher", return_value=None),
    ):
        LineupOptimizer.optimize([p, make_player("2", {})])

    assert p.ratings == original_ratings


def test_unknown_style_raises():
    from src.team.lineup_optimizer import LineupOptimizer

    players = [make_player(str(i), {}) for i in range(10)]

    with pytest.raises(ValueError):
        LineupOptimizer.optimize(players, style="chaos")
