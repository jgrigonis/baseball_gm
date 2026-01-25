# src/tests/game/test_force_chain.py
from src.game.rules.force_advancement import force_advance_chain, ForcedAdvance


def test_force_chain_empty():
    result = force_advance_chain({}, start_base=1)
    assert result == []


def test_force_chain_single_runner():
    occupied = {1: "r1"}

    result = force_advance_chain(occupied, start_base=1)

    assert result == [ForcedAdvance("r1", 1, 2)]


def test_force_chain_stops_at_gap():
    occupied = {
        1: "r1",
        3: "r3",  # gap at 2
    }

    result = force_advance_chain(occupied, start_base=1)

    assert result == [ForcedAdvance("r1", 1, 2)]


def test_force_chain_collision_safe_order():
    occupied = {
        1: "r1",
        2: "r2",
        3: "r3",
    }

    result = force_advance_chain(occupied, start_base=1)

    assert [f.runner for f in result] == ["r3", "r2", "r1"]


def test_force_chain_bases_loaded_walk():
    occupied = {
        1: "r1",
        2: "r2",
        3: "r3",
    }

    result = force_advance_chain(occupied, start_base=1)

    assert result[0].to_base == 4  # runner scores
