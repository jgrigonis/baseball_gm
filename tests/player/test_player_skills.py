# tests/player/test_player_skills.py
"""
What we are testing (by design)

PlayerSkills must:
✅ Be immutable
✅ Behave like a read-only mapping
✅ Support [], in, items(), as_dict()
✅ Construct safely from partial rows
✅ Generate deterministic output when RNG is seeded
✅ Clamp generated stats to valid bounds
✅ Apply left-handed catcher rule correctly
❌ Never require attribute-style access
"""

import pytest
import random

from src.player.player_skills import PlayerSkills, DEFAULT_SKILL_MEAN
from src.player.positions import SKILLS
from src.player.skill_map import SKILL_MIN, SKILL_MAX


class TestPlayerSkillsInitialization:
    """Test creating PlayerSkills instances."""

    def test_init_with_all_skills(self):
        skills_dict = {skill: 50 for skill in SKILLS}
        ps = PlayerSkills(skills_dict)
        assert ps["power"] == 50
        assert ps["speed"] == 50

    def test_init_with_partial_skills_uses_defaults(self):
        skills_dict = {"power": 80, "speed": 60}
        ps = PlayerSkills(skills_dict)
        assert ps["power"] == 80
        assert ps["speed"] == 60
        assert ps["accuracy"] == DEFAULT_SKILL_MEAN

    def test_init_with_empty_dict_uses_all_defaults(self):
        ps = PlayerSkills({})
        for skill in SKILLS:
            assert ps[skill] == DEFAULT_SKILL_MEAN

    def test_init_validates_skill_range_too_high(self):
        with pytest.raises(ValueError, match="out of range"):
            PlayerSkills({"power": 101})

    def test_init_validates_skill_range_too_low(self):
        with pytest.raises(ValueError, match="out of range"):
            PlayerSkills({"power": 0})

    def test_init_validates_skill_range_negative(self):
        with pytest.raises(ValueError, match="out of range"):
            PlayerSkills({"power": -10})

    def test_init_allows_min_value(self):
        ps = PlayerSkills({"power": SKILL_MIN})
        assert ps["power"] == SKILL_MIN

    def test_init_allows_max_value(self):
        ps = PlayerSkills({"power": SKILL_MAX})
        assert ps["power"] == SKILL_MAX

    def test_init_skip_validation(self):
        """With validate=False, should allow out-of-range values."""
        ps = PlayerSkills({"power": 150}, validate=False)
        assert ps["power"] == 150

    def test_init_converts_string_to_int(self):
        ps = PlayerSkills({"power": "85"})
        assert ps["power"] == 85
        assert isinstance(ps["power"], int)

    def test_init_rejects_invalid_string(self):
        with pytest.raises(ValueError, match="invalid value"):
            PlayerSkills({"power": "not_a_number"})

    def test_init_rejects_float_string(self):
        with pytest.raises(ValueError, match="invalid value"):
            ps = PlayerSkills({"power": "85.5"})

            assert ps["power"] == 85  # Truncated to int


class TestDictionaryInterface:
    """Test dictionary-like behavior."""

    @pytest.fixture
    def skills(self):
        return PlayerSkills({"power": 85, "speed": 60, "contact": 70})

    def test_getitem(self, skills):
        assert skills["power"] == 85
        assert skills["speed"] == 60

    def test_getitem_missing_key_raises(self, skills):
        with pytest.raises(KeyError):
            _ = skills["nonexistent_skill"]

    def test_contains(self, skills):
        assert "power" in skills
        assert "speed" in skills
        assert "nonexistent" not in skills

    def test_iter(self, skills):
        skill_names = list(skills)
        assert "power" in skill_names
        assert "speed" in skill_names
        assert len(skill_names) == len(SKILLS)

    def test_len(self, skills):
        assert len(skills) == len(SKILLS)

    def test_get_with_existing_key(self, skills):
        assert skills.get("power") == 85

    def test_get_with_missing_key_returns_none(self, skills):
        assert skills.get("nonexistent") is None

    def test_get_with_default(self, skills):
        assert skills.get("nonexistent", 42) == 42

    def test_keys(self, skills):
        keys = skills.keys()
        assert "power" in keys
        assert len(keys) == len(SKILLS)

    def test_values(self, skills):
        values = list(skills.values())
        assert 85 in values
        assert 60 in values
        assert len(values) == len(SKILLS)

    def test_items(self, skills):
        items = dict(skills.items())
        assert items["power"] == 85
        assert items["speed"] == 60

    def test_as_dict(self, skills):
        d = skills.as_dict()
        assert isinstance(d, dict)
        assert d["power"] == 85
        # Ensure it's a copy
        d["power"] = 999
        assert skills["power"] == 85


class TestImmutability:
    """Test that PlayerSkills is immutable."""

    def test_cannot_modify_via_getitem(self):
        skills = PlayerSkills({"power": 85})
        with pytest.raises(TypeError):
            skills["power"] = 90

    def test_as_dict_returns_copy(self):
        skills = PlayerSkills({"power": 85})
        d = skills.as_dict()
        d["power"] = 999
        assert skills["power"] == 85

    def test_internal_mapping_is_frozen(self):
        skills = PlayerSkills({"power": 85})
        with pytest.raises(TypeError):
            skills._skills["power"] = 90


class TestEquality:
    """Test equality and hashing."""

    def test_equal_skills_are_equal(self):
        skills1 = PlayerSkills({"power": 85, "speed": 60})
        skills2 = PlayerSkills({"power": 85, "speed": 60})
        assert skills1 == skills2

    def test_different_skills_are_not_equal(self):
        skills1 = PlayerSkills({"power": 85, "speed": 60})
        skills2 = PlayerSkills({"power": 80, "speed": 60})
        assert skills1 != skills2

    def test_equal_skills_have_same_hash(self):
        skills1 = PlayerSkills({"power": 85, "speed": 60})
        skills2 = PlayerSkills({"power": 85, "speed": 60})
        assert hash(skills1) == hash(skills2)

    def test_can_use_in_set(self):
        skills1 = PlayerSkills({"power": 85})
        skills2 = PlayerSkills({"power": 85})
        skills3 = PlayerSkills({"power": 90})

        skill_set = {skills1, skills2, skills3}
        assert len(skill_set) == 2  # skills1 and skills2 are equal

    def test_equality_with_non_playerskills(self):
        skills = PlayerSkills({"power": 85})
        assert skills != {"power": 85}
        assert skills != 85
        assert skills != None


class TestStringRepresentation:
    """Test string representations."""

    def test_repr(self):
        skills = PlayerSkills({"power": 85, "speed": 60})
        r = repr(skills)
        assert "PlayerSkills" in r
        assert "power" in r

    def test_str_contains_categories(self):
        skills = PlayerSkills({"power": 85})
        s = str(skills)
        assert "HITTING" in s or "hitting" in s.lower()

    def test_str_contains_skill_values(self):
        player_skills = PlayerSkills({"power": 85})
        s = str(player_skills)
        assert "85" in s


class TestAggregateQueries:
    """Test aggregate methods."""

    def test_average_all_same_value(self):
        skills_dict = {skill: 50 for skill in SKILLS}
        skills = PlayerSkills(skills_dict)
        assert skills.average() == 50.0

    def test_average_mixed_values(self):
        # Set specific values, rest default to 50
        skills = PlayerSkills({"power": 100, "speed": 1})
        avg = skills.average()
        # Most skills are 50, so average should be close to 50
        assert 40 < avg < 60

    def test_total_all_fifty(self):
        skills_dict = {skill: 50 for skill in SKILLS}
        skills = PlayerSkills(skills_dict)
        assert skills.total() == 50 * len(SKILLS)

    def test_total_mixed_values(self):
        skills = PlayerSkills({"power": 100, "speed": 100})
        total = skills.total()
        # power=100, speed=100, rest default to 50
        expected = 100 + 100 + (len(SKILLS) - 2) * 50
        assert total == expected

    def test_get_category_skills_hitting(self):
        skills = PlayerSkills({"power": 85, "eye": 70, "contact": 75})
        hitting_skills = skills.get_category_skills("hitting")

        assert "power" in hitting_skills
        assert hitting_skills["power"] == 85
        assert "eye" in hitting_skills
        assert "contact" in hitting_skills

        # Should not include non-hitting skills
        assert "accuracy" not in hitting_skills

    def test_get_category_skills_defense(self):
        skills = PlayerSkills({"infield": 90, "arm": 80})
        defense_skills = skills.get_category_skills("defense")

        assert "infield" in defense_skills
        assert "arm" in defense_skills
        assert "power" not in defense_skills

    def test_get_category_skills_pitching(self):
        skills = PlayerSkills({"accuracy": 75, "stamina": 80})
        pitching_skills = skills.get_category_skills("pitching")

        assert "accuracy" in pitching_skills
        assert "stamina" in pitching_skills

    def test_get_category_skills_general(self):
        skills = PlayerSkills({"clutch": 85, "speed": 70})
        general_skills = skills.get_category_skills("general")

        assert "clutch" in general_skills
        assert "speed" in general_skills


class TestFromDbRow:
    """Test creating PlayerSkills from database rows."""

    def test_from_db_row_complete(self):
        row = {skill: 50 for skill in SKILLS}
        row["power"] = 85
        row["speed"] = 60

        skills = PlayerSkills.from_db_row(row)
        assert skills["power"] == 85
        assert skills["speed"] == 60

    def test_from_db_row_missing_skills_use_default(self):
        row = {"power": 85}
        skills = PlayerSkills.from_db_row(row)

        assert skills["power"] == 85
        assert skills["speed"] == DEFAULT_SKILL_MEAN

    def test_from_db_row_empty(self):
        skills = PlayerSkills.from_db_row({})
        for skill in SKILLS:
            assert skills[skill] == DEFAULT_SKILL_MEAN


class TestFromCsvRow:
    """Test creating PlayerSkills from CSV rows."""

    def test_from_csv_row_complete(self):
        row = {
            "PO": "85",  # power
            "SP": "60",  # speed
            "CL": "70",  # clutch
            "EY": "50",  # eye
            "CT": "55",  # contact
            "BR": "45",  # base_running
            "BU": "40",  # bunting
            "CA": "30",  # catching
            "IF": "75",  # infield
            "OF": "65",  # outfield
            "AR": "70",  # arm
            "AC": "60",  # accuracy
            "ST": "80",  # stamina
            "RE": "70",  # recovery
            "GB": "55",  # ground_balls
            "KK": "65",  # strikes
            "DU": "50",  # durability
        }

        skills = PlayerSkills.from_csv_row(row)
        assert skills["power"] == 85
        assert skills["speed"] == 60
        assert skills["clutch"] == 70

    def test_from_csv_row_missing_column_raises(self):
        row = {"PO": "85"}  # Missing most columns
        with pytest.raises(ValueError, match="Missing required CSV column"):
            PlayerSkills.from_csv_row(row)

    def test_from_csv_row_invalid_value_raises(self):
        row = {
            "PO": "not_a_number",
            "SP": "60",
            "CL": "70",
            "EY": "50",
            "CT": "55",
            "BR": "45",
            "BU": "40",
            "CA": "30",
            "IF": "75",
            "OF": "65",
            "AR": "70",
            "AC": "60",
            "ST": "80",
            "RE": "70",
            "GB": "55",
            "KK": "65",
        }

        with pytest.raises(ValueError, match="Invalid value"):
            PlayerSkills.from_csv_row(row)


class TestGenerate:
    """Test random skill generation."""

    @pytest.fixture
    def rng(self):
        return random.Random(42)

    def test_generate_creates_all_skills(self, rng):
        skills = PlayerSkills.generate(rng, "ss")
        assert len(skills) == len(SKILLS)

    def test_generate_shortstop_has_high_infield(self, rng):
        skills = PlayerSkills.generate(rng, "ss")
        # SS should have above-average infield skill
        assert skills["infield"] > 50

    def test_generate_pitcher_has_high_stamina(self, rng):
        skills = PlayerSkills.generate(rng, "sp")
        # SP should have above-average stamina
        assert skills["stamina"] > 50

    def test_generate_first_baseman_has_high_power(self, rng):
        skills = PlayerSkills.generate(rng, "1b")
        # 1B should have above-average power
        assert skills["power"] > 50

    def test_generate_with_same_seed_produces_same_skills(self):
        rng1 = random.Random(123)
        rng2 = random.Random(123)

        skills1 = PlayerSkills.generate(rng1, "ss")
        skills2 = PlayerSkills.generate(rng2, "ss")

        assert skills1 == skills2

    def test_generate_with_different_seed_produces_different_skills(self):
        rng1 = random.Random(123)
        rng2 = random.Random(456)

        skills1 = PlayerSkills.generate(rng1, "ss")
        skills2 = PlayerSkills.generate(rng2, "ss")

        assert skills1 != skills2

    def test_generate_left_handed_catcher_has_low_catching(self, rng):
        skills = PlayerSkills.generate(rng, "c", throws="L")
        # Left-handed catchers should have very low catching skill
        assert skills["catching"] < 20

    def test_generate_right_handed_catcher_normal_catching(self, rng):
        skills = PlayerSkills.generate(rng, "c", throws="right")
        # Right-handed catchers should have normal/high catching skill
        assert skills["catching"] > 50

    def test_generate_all_skills_in_valid_range(self, rng):
        for position in ["sp", "c", "ss", "1b", "cf", "dh"]:
            skills = PlayerSkills.generate(rng, position)
            for skill_name, value in skills.items():
                assert SKILL_MIN <= value <= SKILL_MAX, (
                    f"{position} {skill_name} = {value} out of range"
                )


class TestGenerateStat:
    """Test individual stat generation."""

    @pytest.fixture
    def rng(self):
        return random.Random(42)

    def test_generate_stat_default_mean(self, rng):
        values = [PlayerSkills.generate_stat(rng) for _ in range(100)]
        avg = sum(values) / len(values)
        # Should be close to default mean (50)
        assert 45 < avg < 55

    def test_generate_stat_custom_mean(self, rng):
        values = [PlayerSkills.generate_stat(rng, mean=70) for _ in range(100)]
        avg = sum(values) / len(values)
        # Should be close to 70
        assert 65 < avg < 75

    def test_generate_stat_respects_minimum(self, rng):
        values = [
            PlayerSkills.generate_stat(rng, mean=1, minimum=1) for _ in range(100)
        ]
        assert all(v >= 1 for v in values)

    def test_generate_stat_respects_maximum(self, rng):
        values = [
            PlayerSkills.generate_stat(rng, mean=100, maximum=100) for _ in range(100)
        ]
        assert all(v <= 100 for v in values)

    def test_generate_stat_with_custom_sigma(self, rng):
        # Very small sigma should produce values close to mean
        values = [
            PlayerSkills.generate_stat(rng, mean=50, sigma=0.1) for _ in range(100)
        ]
        assert all(49 <= v <= 51 for v in values)

    def test_generate_stat_validates_mean_in_range(self, rng):
        with pytest.raises(ValueError, match="mean"):
            PlayerSkills.generate_stat(rng, mean=150, minimum=1, maximum=100)

    def test_generate_stat_validates_min_less_than_max(self, rng):
        with pytest.raises(ValueError, match="minimum"):
            PlayerSkills.generate_stat(rng, minimum=100, maximum=1)

    def test_generate_stat_low_mean_uses_appropriate_sigma(self, rng):
        # Mean close to minimum should still produce valid values
        values = [PlayerSkills.generate_stat(rng, mean=10) for _ in range(100)]
        assert all(SKILL_MIN <= v <= SKILL_MAX for v in values)

    def test_generate_stat_high_mean_uses_appropriate_sigma(self, rng):
        # Mean close to maximum should still produce valid values
        values = [PlayerSkills.generate_stat(rng, mean=90) for _ in range(100)]
        assert all(SKILL_MIN <= v <= SKILL_MAX for v in values)

    def test_generate_stat_returns_integer(self, rng):
        value = PlayerSkills.generate_stat(rng)
        assert isinstance(value, int)


class TestSerialization:
    """Test serialization methods."""

    def test_to_db_dict(self):
        skills = PlayerSkills({"power": 85, "speed": 60})
        db_dict = skills.to_db_dict()

        assert isinstance(db_dict, dict)
        assert db_dict["power"] == 85
        assert db_dict["speed"] == 60
        assert len(db_dict) == len(SKILLS) + 1  # +1 for age

    def test_to_db_dict_is_mutable_copy(self):
        skills = PlayerSkills({"power": 85})
        db_dict = skills.to_db_dict()

        db_dict["power"] = 999
        assert skills["power"] == 85

    def test_to_csv_dict(self):
        skills = PlayerSkills({"power": 85, "speed": 60, "clutch": 70})
        csv_dict = skills.to_csv_dict()

        assert csv_dict["PO"] == 85  # power
        assert csv_dict["SP"] == 60  # speed
        assert csv_dict["CL"] == 70  # clutch

    def test_to_csv_dict_all_skills(self):
        skills_dict = {skill: 50 for skill in SKILLS}
        skills = PlayerSkills(skills_dict)
        csv_dict = skills.to_csv_dict()

        # Should have same number of entries as SKILL_MAP
        from src.player.skill_map import SKILL_MAP

        assert len(csv_dict) == len(SKILL_MAP)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_all_skills_at_minimum(self):
        skills_dict = {skill: SKILL_MIN for skill in SKILLS}
        skills = PlayerSkills(skills_dict)
        for skill in SKILLS:
            assert skills[skill] == SKILL_MIN

    def test_all_skills_at_maximum(self):
        skills_dict = {skill: SKILL_MAX for skill in SKILLS}
        skills = PlayerSkills(skills_dict)
        for skill in SKILLS:
            assert skills[skill] == SKILL_MAX

    def test_skills_with_zeros_raises(self):
        with pytest.raises(ValueError):
            PlayerSkills({"power": 0})

    def test_skills_with_negative_raises(self):
        with pytest.raises(ValueError):
            PlayerSkills({"power": -10})

    def test_skills_just_above_max_raises(self):
        with pytest.raises(ValueError):
            PlayerSkills({"power": SKILL_MAX + 1})

    def test_empty_initialization(self):
        skills = PlayerSkills({})
        assert len(skills) == len(SKILLS)
        for skill in SKILLS:
            assert skills[skill] == DEFAULT_SKILL_MEAN

    def test_generate_many_positions(self):
        """Test generating skills for all positions."""
        rng = random.Random(42)
        positions = [
            "sp",
            "rp",
            "c",
            "1b",
            "2b",
            "ss",
            "3b",
            "lf",
            "cf",
            "rf",
            "if",
            "of",
            "dh",
        ]

        for position in positions:
            skills = PlayerSkills.generate(rng, position)
            assert len(skills) == len(SKILLS)
            for value in skills.values():
                assert SKILL_MIN <= value <= SKILL_MAX


class TestRoundTrip:
    """Test that skills can be serialized and deserialized."""

    def test_roundtrip_via_db_dict(self):
        original = PlayerSkills({"power": 85, "speed": 60, "clutch": 70})
        db_dict = original.to_db_dict()
        restored = PlayerSkills(db_dict)

        assert original == restored

    def test_roundtrip_via_csv_dict(self):
        original = PlayerSkills({"power": 85, "speed": 60, "clutch": 70})
        csv_dict = original.to_csv_dict()

        # Build reverse mapping for restoration
        from src.player.skill_map import SKILL_MAP

        full_dict = {}
        for abbr, value in csv_dict.items():
            skill_name = SKILL_MAP[abbr]
            full_dict[skill_name] = value

        restored = PlayerSkills(full_dict)
        assert restored["power"] == 85
        assert restored["speed"] == 60
        assert restored["clutch"] == 70


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_generate_and_serialize(self):
        rng = random.Random(42)
        skills = PlayerSkills.generate(rng, "ss")

        # Should be able to serialize to both formats
        db_dict = skills.to_db_dict()
        csv_dict = skills.to_csv_dict()

        assert len(db_dict) == len(SKILLS) + 1  # +1 for age
        assert len(csv_dict) > 0

    def test_create_modify_copy_original_unchanged(self):
        original = PlayerSkills({"power": 85})
        copy_dict = original.as_dict()
        copy_dict["power"] = 10

        modified = PlayerSkills(copy_dict)

        assert original["power"] == 85
        assert modified["power"] == 10

    def test_multiple_skill_categories(self):
        skills = PlayerSkills(
            {
                "power": 90,  # hitting
                "accuracy": 80,  # pitching
                "infield": 70,  # defense
                "clutch": 85,  # general
            }
        )

        hitting = skills.get_category_skills("hitting")
        pitching = skills.get_category_skills("pitching")
        defense = skills.get_category_skills("defense")
        general = skills.get_category_skills("general")

        assert hitting["power"] == 90
        assert pitching["accuracy"] == 80
        assert defense["infield"] == 70
        assert general["clutch"] == 85


# # tests/player/test_player_skills.py
# """
# What we are testing (by design)

# PlayerSkills must:
# ✅ Be immutable
# ✅ Behave like a read-only mapping
# ✅ Support [], in, items(), as_dict()
# ✅ Construct safely from partial rows
# ✅ Generate deterministic output when RNG is seeded
# ✅ Clamp generated stats to valid bounds
# ✅ Apply left-handed catcher rule correctly
# ❌ Never require attribute-style access
# """

# import random
# import pytest

# from src.player.player_skills import PlayerSkills
# from src.player.positions import SKILLS


# def test_player_skills_basic_access():
#     """Construction & mapping behavior"""
#     skills = PlayerSkills({"power": 50, "speed": 60})

#     assert skills["power"] == 50
#     assert skills["speed"] == 60


# def test_player_skills_no_attribute_access():
#     """
#     Mapping-only access (no attribute access)

#     This enforces your architectural decision forever.
#     """
#     skills = PlayerSkills({"power": 50})

#     with pytest.raises(AttributeError):
#         _ = skills.power


# def test_player_skills_as_dict_returns_copy():
#     """.as_dict() returns a copy"""
#     skills = PlayerSkills({"power": 50})

#     d = skills.as_dict()
#     d["power"] = 99

#     assert skills["power"] == 50


# def test_player_skills_is_immutable():
#     """Immutability is enforced"""
#     skills = PlayerSkills({"power": 50})

#     with pytest.raises(TypeError):
#         skills._skills["power"] = 99


# def test_player_skills_repr():
#     """__repr__ is stable and informative"""
#     skills = PlayerSkills({"power": 50})

#     rep = repr(skills)
#     assert rep.startswith("PlayerSkills(")
#     assert "power" in rep


# def test_player_skills_from_row_fills_missing():
#     """
#     from_db_row fills missing skills with zero

#     This is critical for CSV/db safety.
#     """
#     row = {"power": 80}

#     skills = PlayerSkills.from_db_row(row)

#     for skill in SKILLS:
#         assert skill in skills

#     assert skills["power"] == 80


# def test_generate_stat_clamps_bounds():
#     """
#     generate_stat clamps to bounds

#     We force extreme RNG output to ensure clamping works.
#     """
#     rng = random.Random(0)

#     high = PlayerSkills.generate_stat(rng, minimum=1, maximum=100, mean=1000)
#     low = PlayerSkills.generate_stat(rng, minimum=1, maximum=100, mean=-1000)

#     assert 1 <= high <= 100
#     assert 1 <= low <= 100


# def test_generate_is_deterministic_with_seed():
#     """
#     generate is deterministic with seeded RNG

#     This is huge for simulations and tests.
#     """
#     rng1 = random.Random(123)
#     rng2 = random.Random(123)

#     s1 = PlayerSkills.generate(rng1, position="cf", throws="right")
#     s2 = PlayerSkills.generate(rng2, position="cf", throws="right")

#     assert s1.as_dict() == s2.as_dict()


# def test_left_handed_catcher_rule():
#     """
#     Left-handed catcher rule is enforced
#     """
#     rng = random.Random(42)

#     skills = PlayerSkills.generate(rng, position="c", throws="left")

#     assert skills["catching"] <= 20  # mean forced to 10
