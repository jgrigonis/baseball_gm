# tests/game/test_intents.py

import pytest
from src.game.intents.pitch import PitchIntent, PrePitchSituation
from src.game.intents.pick_off import PickOffIntent


class TestPrePitchSituation:
    """Test PrePitchSituation intent component"""

    def test_default_values(self):
        """Test that all defaults are set correctly"""
        sit = PrePitchSituation()

        assert sit.steal_attempt is None
        assert sit.double_steal_attempt is None
        assert sit.bunt_attempt is False
        assert sit.hit_and_run is False
        assert sit.pitch_out is False
        assert sit.intentional_walk is False
        assert sit.pickoff_attempt is None

    def test_immutability(self):
        """Test that PrePitchSituation is frozen"""
        sit = PrePitchSituation(steal_attempt=1)

        with pytest.raises(AttributeError):
            sit.steal_attempt = 2

    def test_steal_attempt(self):
        """Test setting steal attempt"""
        sit = PrePitchSituation(steal_attempt=1)
        assert sit.steal_attempt == 1

    def test_double_steal_attempt(self):
        """Test setting double steal attempt"""
        sit = PrePitchSituation(double_steal_attempt=[1, 2])
        assert sit.double_steal_attempt == [1, 2]

    def test_bunt_attempt(self):
        """Test setting bunt attempt"""
        sit = PrePitchSituation(bunt_attempt=True)
        assert sit.bunt_attempt is True

    def test_hit_and_run(self):
        """Test setting hit and run"""
        sit = PrePitchSituation(hit_and_run=True)
        assert sit.hit_and_run is True

    def test_pitch_out(self):
        """Test setting pitch out"""
        sit = PrePitchSituation(pitch_out=True)
        assert sit.pitch_out is True

    def test_intentional_walk(self):
        """Test setting intentional walk"""
        sit = PrePitchSituation(intentional_walk=True)
        assert sit.intentional_walk is True

    def test_pickoff_attempt(self):
        """Test setting pickoff attempt"""
        sit = PrePitchSituation(pickoff_attempt=2)
        assert sit.pickoff_attempt == 2


class TestPitchIntent:
    """Test PitchIntent"""

    @pytest.fixture
    def mock_players(self):
        """Create mock players for testing"""
        from src.player.player_factory import PlayerFactory

        pf = PlayerFactory()
        pitcher = pf.create()
        batter = pf.create()

        return pitcher, batter

    def test_basic_creation(self, mock_players):
        """Test creating a basic pitch intent"""
        pitcher, batter = mock_players

        intent = PitchIntent(pitcher=pitcher, batter=batter)

        assert intent.pitcher == pitcher
        assert intent.batter == batter
        assert intent.pre_pitch_situation is None

    def test_immutability(self, mock_players):
        """Test that PitchIntent is frozen"""
        pitcher, batter = mock_players
        intent = PitchIntent(pitcher=pitcher, batter=batter)

        with pytest.raises(AttributeError):
            intent.pitcher = batter

    def test_with_pre_pitch_situation(self, mock_players):
        """Test creating pitch intent with tactical situation"""
        pitcher, batter = mock_players
        situation = PrePitchSituation(steal_attempt=1)

        intent = PitchIntent(
            pitcher=pitcher, batter=batter, pre_pitch_situation=situation
        )

        assert intent.pre_pitch_situation == situation
        assert intent.pre_pitch_situation.steal_attempt == 1

    def test_to_dict_without_situation(self, mock_players):
        """Test serialization without pre-pitch situation"""
        pitcher, batter = mock_players
        intent = PitchIntent(pitcher=pitcher, batter=batter)

        data = intent.to_dict()

        assert data["type"] == "PitchIntent"
        assert data["pitcher_id"] == pitcher.id
        assert data["batter_id"] == batter.id
        assert data["situation"] is None

    def test_to_dict_with_situation(self, mock_players):
        """Test serialization with pre-pitch situation"""
        pitcher, batter = mock_players
        situation = PrePitchSituation(steal_attempt=1, bunt_attempt=True)
        intent = PitchIntent(
            pitcher=pitcher, batter=batter, pre_pitch_situation=situation
        )

        data = intent.to_dict()

        assert data["type"] == "PitchIntent"
        assert data["situation"]["steal_attempt"] == 1
        assert data["situation"]["bunt_attempt"] is True

    def test_serialization_round_trip(self, mock_players):
        """Test that to_dict/from_dict round-trip correctly"""
        from unittest.mock import Mock

        pitcher, batter = mock_players

        # Create a mock game that returns the right players
        mock_game = Mock()
        mock_game.current_pitcher = pitcher
        mock_game.get_player = Mock(return_value=batter)

        situation = PrePitchSituation(
            steal_attempt=2, hit_and_run=True, pitch_out=False
        )

        original = PitchIntent(
            pitcher=pitcher, batter=batter, pre_pitch_situation=situation
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = PitchIntent.from_dict(data, mock_game)

        # Verify round-trip
        assert restored.pitcher.id == original.pitcher.id
        assert restored.batter.id == original.batter.id
        assert (
            restored.pre_pitch_situation.steal_attempt
            == original.pre_pitch_situation.steal_attempt
        )
        assert (
            restored.pre_pitch_situation.hit_and_run
            == original.pre_pitch_situation.hit_and_run
        )
        assert (
            restored.pre_pitch_situation.pitch_out
            == original.pre_pitch_situation.pitch_out
        )

    def test_has_intent_id(self, mock_players):
        """Test that intent has unique ID"""
        pitcher, batter = mock_players
        intent = PitchIntent(pitcher=pitcher, batter=batter)

        assert intent.intent_id is not None

    def test_unique_intent_ids(self, mock_players):
        """Test that each intent gets unique ID"""
        pitcher, batter = mock_players

        intent1 = PitchIntent(pitcher=pitcher, batter=batter)
        intent2 = PitchIntent(pitcher=pitcher, batter=batter)

        assert intent1.intent_id != intent2.intent_id


class TestPickOffIntent:
    """Test PickOffIntent"""

    @pytest.fixture
    def mock_pitcher(self):
        """Create mock pitcher for testing"""
        from src.player.player_factory import PlayerFactory

        pf = PlayerFactory()
        return pf.create()

    def test_basic_creation(self, mock_pitcher):
        """Test creating a pickoff intent"""
        intent = PickOffIntent(pitcher=mock_pitcher, target_base=1)

        assert intent.pitcher == mock_pitcher
        assert intent.target_base == 1

    def test_immutability(self, mock_pitcher):
        """Test that PickOffIntent is frozen"""
        intent = PickOffIntent(pitcher=mock_pitcher, target_base=2)

        with pytest.raises(AttributeError):
            intent.target_base = 3

    def test_target_base_is_int(self, mock_pitcher):
        """Test that target_base accepts int values"""
        for base in [1, 2, 3]:
            intent = PickOffIntent(pitcher=mock_pitcher, target_base=base)
            assert intent.target_base == base
            assert isinstance(intent.target_base, int)

    def test_has_intent_id(self, mock_pitcher):
        """Test that intent has unique ID"""
        intent = PickOffIntent(pitcher=mock_pitcher, target_base=1)

        assert intent.intent_id is not None

    def test_unique_intent_ids(self, mock_pitcher):
        """Test that each intent gets unique ID"""
        intent1 = PickOffIntent(pitcher=mock_pitcher, target_base=1)
        intent2 = PickOffIntent(pitcher=mock_pitcher, target_base=1)

        assert intent1.intent_id != intent2.intent_id


class TestGameIntent:
    """Test GameIntent base class"""

    @pytest.fixture
    def mock_players(self):
        """Create mock players for testing"""
        from src.player.player_factory import PlayerFactory

        pf = PlayerFactory()
        pitcher = pf.create()
        batter = pf.create()

        return pitcher, batter

    def test_intents_have_unique_ids(self, mock_players):
        """Test that different intent types have unique IDs"""
        pitcher, batter = mock_players

        pitch_intent = PitchIntent(pitcher=pitcher, batter=batter)
        pickoff_intent = PickOffIntent(pitcher=pitcher, target_base=1)

        assert pitch_intent.intent_id != pickoff_intent.intent_id
