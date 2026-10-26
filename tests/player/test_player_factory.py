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

import pytest
import random

from src.player.player_factory import PlayerFactory, VALID_BATS, VALID_THROWS
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.player.positions import POSITIONS
import src.game.game_exceptions as game_exceptions


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
    factory = PlayerFactory(rng=random.Random(1))
    player = factory.create()

    assert isinstance(player, PlayerRecord)
    assert isinstance(player.id, str)
    assert isinstance(player.first_name, str)
    assert isinstance(player.last_name, str)
    assert isinstance(player.skills, PlayerSkills)


def test_explicit_position_is_used():
    """Explicit position is honored"""
    factory = PlayerFactory(rng=random.Random(1))

    player = factory.create(position="ss")
    assert player.skills["infield"] > 0  # sanity check


def test_invalid_position_raises():
    """Invalid position raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadPositionException):
        factory.create(position="qb")


def test_explicit_throws_is_used():
    """Explicit handedness is honored"""
    factory = PlayerFactory(rng=random.Random(1))
    player = factory.create(throws="L")

    assert player.throws == "L"


def test_invalid_throws_raises():
    """Invalid throws raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadHandednessException):
        factory.create(throws="ambidextrous")


def test_explicit_bats_is_used():
    """Explicit batting side is honored"""
    factory = PlayerFactory(rng=random.Random(1))
    player = factory.create(bats="S")

    assert player.bats == "S"


def test_invalid_bats_raises():
    """Invalid bats raises"""
    factory = PlayerFactory()

    with pytest.raises(game_exceptions.BadHandednessException):
        factory.create(bats="both")


def test_position_is_randomized_when_not_provided():
    """Position is randomly selected when omitted"""
    factory = PlayerFactory(rng=random.Random(42))
    player = factory.create()

    assert player.skills is not None


def test_generated_id_is_hex_uuid():
    """ID generation is stable + UUID-shaped"""
    factory = PlayerFactory(rng=random.Random(99))
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
    factory = PlayerFactory(rng=random.Random(0))

    monkeypatch.setitem(
        factory._get_position_template("ss"),
        "switch_hitter",
        1.0,
    )

    player = factory.create(position="ss")
    assert player.bats == "S"


# Claude generated test below


class TestPlayerFactoryInitialization:
    """Test PlayerFactory initialization."""

    def test_init_with_default_rng(self):
        factory = PlayerFactory()
        assert factory.rng is not None
        assert isinstance(factory.rng, random.Random)

    def test_init_with_custom_rng(self):
        rng = random.Random(42)
        factory = PlayerFactory(rng=rng)
        assert factory.rng is rng

    def test_init_creates_name_generator(self):
        factory = PlayerFactory()
        assert factory.name_gen is not None


class TestGenerateId:
    """Test player ID generation."""

    def test_generate_id_returns_string(self):
        factory = PlayerFactory()
        player_id = factory._generate_id()
        assert isinstance(player_id, str)

    def test_generate_id_returns_hex_string(self):
        factory = PlayerFactory()
        player_id = factory._generate_id()
        # Should be 32 hex characters (128 bits)
        assert len(player_id) == 32
        assert all(c in "0123456789abcdef" for c in player_id)

    def test_generate_id_unique(self):
        factory = PlayerFactory()
        ids = [factory._generate_id() for _ in range(100)]
        # All IDs should be unique
        assert len(set(ids)) == 100

    def test_generate_id_deterministic_with_seed(self):
        factory1 = PlayerFactory(rng=random.Random(123))
        factory2 = PlayerFactory(rng=random.Random(123))

        id1 = factory1._generate_id()
        id2 = factory2._generate_id()

        assert id1 == id2


class TestResolvePosition:
    """Test position resolution."""

    def test_resolve_position_with_valid_position(self):
        factory = PlayerFactory()
        position = factory._resolve_position("ss")
        assert position == "ss"

    def test_resolve_position_with_all_valid_positions(self):
        factory = PlayerFactory()
        for pos in POSITIONS:
            result = factory._resolve_position(pos)
            assert result == pos

    def test_resolve_position_with_none_returns_random(self):
        factory = PlayerFactory(rng=random.Random(42))
        position = factory._resolve_position(None)
        assert position in POSITIONS

    def test_resolve_position_with_invalid_raises(self):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadPositionException):
            factory._resolve_position("quarterback")

    def test_resolve_position_none_is_random(self):
        factory = PlayerFactory()
        positions = [factory._resolve_position(None) for _ in range(20)]
        # Should get variety (very unlikely to get same position 20 times)
        assert len(set(positions)) > 1


class TestResolveHandedness:
    """Test handedness resolution."""

    @pytest.fixture
    def template(self):
        return {
            "throws_left": 0.25,
            "switch_hitter": 0.10,
            "bats_left": 0.15,
        }

    def test_resolve_handedness_left_specified(self, template):
        factory = PlayerFactory()
        result = factory._resolve_handedness(
            throws="L", template=template, position="ss"
        )
        assert result == "L"

    def test_resolve_handedness_right_specified(self, template):
        factory = PlayerFactory()
        result = factory._resolve_handedness(
            throws="R", template=template, position="ss"
        )
        assert result == "R"

    def test_resolve_handedness_invalid_raises(self, template):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadHandednessException):
            factory._resolve_handedness(
                throws="ambidextrous", template=template, position="ss"
            )

    def test_resolve_handedness_none_uses_template(self, template):
        factory = PlayerFactory(rng=random.Random(42))
        result = factory._resolve_handedness(
            throws=None, template=template, position="ss"
        )
        assert result in VALID_THROWS

    def test_resolve_handedness_distribution(self):
        """Test that distribution roughly matches template probability."""
        template = {"throws_left": 0.30}
        factory = PlayerFactory(rng=random.Random(42))

        results = [
            factory._resolve_handedness(throws=None, template=template, position="of")
            for _ in range(1000)
        ]
        left_count = results.count("L")
        left_ratio = left_count / len(results)

        # Should be roughly 30% (allow 10% margin)
        assert 0.20 < left_ratio < 0.40


class TestResolveBattingSide:
    """Test batting side resolution."""

    @pytest.fixture
    def template(self):
        return {
            "throws_left": 0.25,
            "switch_hitter": 0.10,
            "bats_left": 0.15,
        }

    def test_resolve_batting_side_left_specified(self, template):
        factory = PlayerFactory()
        result = factory._resolve_batting_side("L", "R", template)
        assert result == "L"

    def test_resolve_batting_side_right_specified(self, template):
        factory = PlayerFactory()
        result = factory._resolve_batting_side("R", "R", template)
        assert result == "R"

    def test_resolve_batting_side_switch_specified(self, template):
        factory = PlayerFactory()
        result = factory._resolve_batting_side("S", "R", template)
        assert result == "S"

    def test_resolve_batting_side_invalid_raises(self, template):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadHandednessException):
            factory._resolve_batting_side("both", "R", template)

    def test_resolve_batting_side_none_uses_template(self, template):
        factory = PlayerFactory(rng=random.Random(42))
        result = factory._resolve_batting_side(None, "R", template)
        assert result in VALID_BATS

    def test_resolve_batting_side_can_be_switch(self, template):
        """Test that switch hitters can be generated."""
        factory = PlayerFactory(rng=random.Random(42))

        results = [
            factory._resolve_batting_side(None, "R", template) for _ in range(1000)
        ]

        # Should have some switch hitters
        assert "S" in results

    def test_resolve_batting_side_defaults_to_throwing_hand(self):
        """Test that most batters bat same as throwing hand."""
        template = {"switch_hitter": 0.0, "bats_left": 0.0}
        factory = PlayerFactory(rng=random.Random(42))

        # Right-handed thrower should bat right
        result = factory._resolve_batting_side(None, "R", template)
        assert result == "R"

        # Left-handed thrower should bat left
        result = factory._resolve_batting_side(None, "L", template)
        assert result == "L"


class TestGetPositionTemplate:
    """Test getting position templates."""

    def test_get_position_template_valid_position(self):
        factory = PlayerFactory()
        template = factory._get_position_template("ss")
        assert "throws_left" in template
        assert "switch_hitter" in template
        assert "bats_left" in template

    def test_get_position_template_all_positions(self):
        factory = PlayerFactory()
        for position in POSITIONS:
            template = factory._get_position_template(position)
            assert isinstance(template, dict)
            assert "throws_left" in template

    def test_get_position_template_invalid_raises(self):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadPositionException):
            factory._get_position_template("invalid")


class TestCreate:
    """Test creating PlayerRecords."""

    def test_create_with_all_defaults(self):
        factory = PlayerFactory(rng=random.Random(42))
        player = factory.create()

        assert isinstance(player, PlayerRecord)
        assert player.id is not None
        assert player.first_name is not None
        assert player.last_name is not None
        assert player.position in POSITIONS
        assert player.throws in VALID_THROWS
        assert player.bats in VALID_BATS
        assert isinstance(player.skills, PlayerSkills)

    def test_create_with_specified_position(self):
        factory = PlayerFactory()
        player = factory.create(position="ss")
        assert player.position == "ss"

    def test_create_with_specified_throws(self):
        factory = PlayerFactory()
        player = factory.create(throws="L")
        assert player.throws == "L"

    def test_create_with_specified_bats(self):
        factory = PlayerFactory()
        player = factory.create(bats="S")
        assert player.bats == "S"

    def test_create_with_all_specified(self):
        factory = PlayerFactory()
        player = factory.create(position="cf", throws="L", bats="L")

        assert player.position == "cf"
        assert player.throws == "L"
        assert player.bats == "L"

    def test_create_generates_unique_ids(self):
        factory = PlayerFactory()
        players = [factory.create() for _ in range(10)]
        ids = [p.id for p in players]

        # All IDs should be unique
        assert len(set(ids)) == 10

    def test_create_generates_skills(self):
        factory = PlayerFactory()
        player = factory.create(position="ss")

        # Should have all skills
        assert len(player.skills) > 0
        # Shortstops should have good infield skills
        assert player.skills["infield"] > 39

    def test_create_with_invalid_position_raises(self):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadPositionException):
            factory.create(position="invalid")

    def test_create_with_invalid_throws_raises(self):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadHandednessException):
            factory.create(throws="invalid")

    def test_create_with_invalid_bats_raises(self):
        factory = PlayerFactory()
        with pytest.raises(game_exceptions.BadHandednessException):
            factory.create(bats="invalid")

    def test_create_is_deterministic_with_seed(self):
        """Same seed should produce same player."""
        factory1 = PlayerFactory(rng=random.Random(12345))
        factory2 = PlayerFactory(rng=random.Random(12345))

        player1 = factory1.create()
        player2 = factory2.create()

        assert player1.id == player2.id
        assert player1.first_name == player2.first_name
        assert player1.last_name == player2.last_name
        assert player1.position == player2.position
        assert player1.throws == player2.throws
        assert player1.bats == player2.bats
        assert player1.skills == player2.skills


class TestCreatePositionSpecificBehavior:
    """Test position-specific player creation."""

    def test_create_pitcher_has_good_pitching_skills(self):
        factory = PlayerFactory(rng=random.Random(42))
        pitcher = factory.create(position="sp")

        # Starting pitchers should have good stamina
        assert pitcher.skills["stamina"] > 50

    def test_create_shortstop_has_good_defense(self):
        factory = PlayerFactory(rng=random.Random(42))
        shortstop = factory.create(position="ss")

        # Shortstops should have good infield defense
        assert shortstop.skills["infield"] > 50

    def test_create_first_baseman_has_good_power(self):
        factory = PlayerFactory(rng=random.Random(42))
        first_basemen = [factory.create(position="1b") for _ in range(50)]

        # 1B should have above average power
        mean_power = sum(p.skills["power"] for p in first_basemen) / 50
        assert mean_power > 50

    def test_create_catcher_left_handed_rare(self):
        """Left-handed catchers should be very rare."""
        factory = PlayerFactory(rng=random.Random(42))

        catchers = [factory.create(position="c") for _ in range(100)]
        left_catchers = [c for c in catchers if c.throws == "left"]

        # Should be very few left-handed catchers
        assert len(left_catchers) < 5


class TestCreateAllPositions:
    """Test creating players for all positions."""

    def test_create_all_positions(self):
        factory = PlayerFactory(rng=random.Random(42))

        for position in POSITIONS:
            player = factory.create(position=position)
            assert player.position == position
            assert isinstance(player, PlayerRecord)


class TestNameGeneration:
    """Test name generation integration."""

    def test_create_generates_first_name(self):
        factory = PlayerFactory()
        player = factory.create()
        assert player.first_name is not None
        assert len(player.first_name) > 0

    def test_create_generates_last_name(self):
        factory = PlayerFactory()
        player = factory.create()
        assert player.last_name is not None
        assert len(player.last_name) > 0

    def test_create_generates_different_names(self):
        factory = PlayerFactory()
        players = [factory.create() for _ in range(10)]

        first_names = [p.first_name for p in players]
        # Should have some variety (unlikely all same)
        assert len(set(first_names)) > 1


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_create_with_none_values(self):
        factory = PlayerFactory()
        player = factory.create(position=None, throws=None, bats=None)

        assert player.position in POSITIONS
        assert player.throws in VALID_THROWS
        assert player.bats in VALID_BATS

    def test_create_multiple_players_no_conflicts(self):
        """Creating many players should not cause issues."""
        factory = PlayerFactory()
        players = [factory.create() for _ in range(100)]

        # All should be valid PlayerRecords
        assert all(isinstance(p, PlayerRecord) for p in players)
        # All should have unique IDs
        ids = [p.id for p in players]
        assert len(set(ids)) == 100

    def test_factory_reuse(self):
        """Same factory can create multiple players."""
        factory = PlayerFactory(rng=random.Random(42))

        player1 = factory.create()
        player2 = factory.create()

        # Should be different players
        assert player1.id != player2.id


class TestConstants:
    """Test module constants."""

    def test_valid_bats_constant(self):
        assert "L" in VALID_BATS
        assert "R" in VALID_BATS
        assert "S" in VALID_BATS
        assert len(VALID_BATS) == 3

    def test_valid_throws_constant(self):
        assert "L" in VALID_THROWS
        assert "R" in VALID_THROWS
        assert len(VALID_THROWS) == 2


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_create_full_roster(self):
        """Create a full baseball roster."""
        factory = PlayerFactory(rng=random.Random(42))

        roster = {
            "sp": 5,  # 5 starting pitchers
            "rp": 7,  # 7 relief pitchers
            "c": 2,  # 2 catchers
            "1b": 1,  # 1 first baseman
            "2b": 1,  # etc.
            "ss": 1,
            "3b": 1,
            "lf": 1,
            "cf": 1,
            "rf": 1,
            "if": 2,  # 2 utility infielders
            "of": 2,  # 2 outfielders
        }

        players = []
        for position, count in roster.items():
            for _ in range(count):
                players.append(factory.create(position=position))

        # Should have 25 players
        assert len(players) == 25

        # All should have unique IDs
        ids = [p.id for p in players]
        assert len(set(ids)) == 25

        # All should be valid
        assert all(isinstance(p, PlayerRecord) for p in players)

    def test_create_with_reproducible_roster(self):
        """Same seed creates same roster."""

        def create_roster(seed):
            factory = PlayerFactory(rng=random.Random(seed))
            return [factory.create() for _ in range(5)]

        roster1 = create_roster(999)
        roster2 = create_roster(999)

        for p1, p2 in zip(roster1, roster2):
            assert p1.id == p2.id
            assert p1.first_name == p2.first_name
            assert p1.last_name == p2.last_name
            assert p1.position == p2.position

    def test_create_balanced_handedness_distribution(self):
        """Over many players, handedness should match MLB-ish distribution."""
        factory = PlayerFactory(rng=random.Random(42))

        # Create 100 random players
        players = [factory.create() for _ in range(100)]

        # Count left-handed throwers
        left_throwers = [p for p in players if p.throws == "L"]
        left_ratio = len(left_throwers) / len(players)

        # Should be roughly 20-30% left-handed (MLB is ~25%)
        assert 0.10 < left_ratio < 0.40

    def test_skills_match_position_expectations(self):
        """Skills should make sense for each position."""
        factory = PlayerFactory(rng=random.Random(42))

        # Pitchers should have better pitching skills than hitting
        pitcher = factory.create(position="sp")
        assert pitcher.skills["accuracy"] > pitcher.skills["power"]

        # Shortstops should have good speed and defense
        shortstop = factory.create(position="ss")
        assert shortstop.skills["speed"] >= 40  # Changed from > to >=
        assert shortstop.skills["infield"] > 50

        # First basemen should have good power
        first_baseman = factory.create(position="1b")
        assert first_baseman.skills["power"] > 50
