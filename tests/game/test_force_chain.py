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

    assert [f.runner_id for f in result] == ["r3", "r2", "r1"]


def test_force_chain_bases_loaded_walk():
    occupied = {
        1: "r1",
        2: "r2",
        3: "r3",
    }

    result = force_advance_chain(occupied, start_base=1)

    assert result[0].to_base == 4  # runner scores


# OLD STUFF BELOW
#  from types import SimpleNamespace
# from src.game.bases import Bases
# from src.game.resolver import Resolver

# def test_force_chain_returns_collision_safe_order():
#     bases = Bases()
#     bases._bases = {
#         1: "A",
#         2: "B",
#         3: "C",
#     }

#     game = SimpleNamespace(bases=bases)

#     resolver = Resolver(rng=None)  # rng unused here

#     events = resolver._force_advance_chain(game, starting_base=1)

#     assert [e.from_base for e in events] == [3, 2, 1]
#     assert [e.to_base for e in events] == [4, 3, 2]

# def test_force_chain_stops_at_gap():
#     bases = Bases()
#     bases._bases = {1: "A", 3: "C"}  # gap at 2

#     game = SimpleNamespace(bases=bases)
#     resolver = Resolver(rng=None)

#     events = resolver._force_advance_chain(game, starting_base=1)

#     # only runner on 1 is forced
#     assert len(events) == 1
#     assert events[0].from_base == 1
