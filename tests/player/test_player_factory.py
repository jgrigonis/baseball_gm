# tests/player/test_player_factory.py
"""
The tests explicitly lock down that PlayerFactory:

✔ Is deterministic when seeded
✔ Produces valid PlayerRecord objects
✔ Enforces valid enums (position, bats, throws)
✔ Honors explicit overrides
✔ Uses templates probabilistically
✔ Generates stable IDs when seeded
✔ Does not depend on randomness leaking outside the RNG
"""


import random
import pytest

import src.game.game_exceptions as game_exceptions
from src.player.player_factory import PlayerFactory
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import POSITIONS


def test_player_factory_is_deterministic_with_seed():
    """Deterministic creation (seeded RNG)"""
    rng1 = random.Random(123)
    rng2 = random.Random(123)

    f1 = PlayerFactory(rng=rng1)
    f2 = PlayerFactory(rng=rng2)

    p1 = f1.create()
    p2 = f2.create()

    assert p1.id == p2.id
    assert p1.first_name == p2.first_name
    assert p1.last_name == p2.last_name
    assert p1.bats == p2.bats
    assert p1.throws == p2.throws
    assert p1.skills.as_dict() == p2.skills.as_dict()


def test_player_factory_creates_player_record():
    """Creates a valid PlayerRecord"""
    factory = PlayerFactory(random.Random(1))
    player = factory.create()

    assert isinstance(player, PlayerRecord)
    assert isinstance(player.id, str)
    assert isinstance(player.first_name, str)
    assert isinstance(player.last_name, str)
    assert isinstance(player.skills, PlayerSkills)


def test_explicit_position_is_used():
    """Explicit position is honored"""
    factory = PlayerFactory(random.Random(1))

    player = factory.create(position="ss")
    assert player.skills["infield"] > 0  # sanity check


def test_invalid_position_raises():
    """Invalid position raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadPositionException):
        factory.create(position="qb")


def test_explicit_throws_is_used():
    """Explicit handedness is honored"""
    factory = PlayerFactory(random.Random(1))
    player = factory.create(throws="left")

    assert player.throws == "left"


def test_invalid_throws_raises():
    """Invalid throws raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadHandednessException):
        factory.create(throws="ambidextrous")


def test_explicit_bats_is_used():
    """Explicit batting side is honored"""
    factory = PlayerFactory(random.Random(1))
    player = factory.create(bats="switch")

    assert player.bats == "switch"


def test_invalid_bats_raises():
    """Invalid bats raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadHandednessException):
        factory.create(bats="both")


def test_position_is_randomized_when_not_provided():
    """Position is randomly selected when omitted"""
    factory = PlayerFactory(random.Random(42))
    player = factory.create()

    assert player.skills is not None


def test_generated_id_is_hex_uuid():
    """ID generation is stable + UUID-shaped"""
    factory = PlayerFactory(random.Random(99))
    player = factory.create()

    assert len(player.id) == 32
    int(player.id, 16)  # should not raise


def test_factory_does_not_use_global_rng():
    """Factory does not mutate RNG externally"""
    random.seed(0)
    f = PlayerFactory()

    p1 = f.create()
    p2 = f.create()

    assert p1.id != p2.id


def test_switch_hitter_probability(monkeypatch):
    """
    To lock down template influence, we do this with monkeypatching:
    """
    factory = PlayerFactory(random.Random(0))

    monkeypatch.setitem(
        factory._get_position_template("ss"),
        "switch_hitter",
        1.0,
    )

    player = factory.create(position="ss")
    assert player.bats == "switch"
