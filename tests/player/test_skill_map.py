# tests/test_skill_map.py
import pytest
from src.player.skill_map import (
    SKILL_MAP,
    SKILL_ABBREVIATIONS,
    SKILL_CATEGORIES,
    SKILL_MIN,
    SKILL_MAX,
    ALL_SKILL_ABBRS,
    ALL_SKILL_NAMES,
    BATTER_SKILLS,
    PITCHER_SKILLS,
    FIELDER_SKILLS,
    get_skill_name,
    get_skill_abbr,
    is_valid_skill,
    is_valid_skill_value,
    validate_skill_value,
    get_skills_by_category,
    get_skill_category,
    get_all_skills,
    format_skill_display,
    get_category_display_name,
)
from src.player.positions import SKILLS

"""
First tests here are mapping integrity tests, not value tests.
"""


def test_skill_map_targets_are_valid_skills():
    """All mapped values are valid skills"""
    for abbr, skill in SKILL_MAP.items():
        assert skill in SKILLS, f"{abbr} maps to unknown skill '{skill}'"


def test_skill_map_keys_are_uppercase_strings():
    for key in SKILL_MAP:
        assert isinstance(key, str)
        assert key.isupper()


def test_skill_map_values_are_lowercase_strings():
    for value in SKILL_MAP.values():
        assert isinstance(value, str)
        assert value == value.lower()


def test_skill_map_values_equals_SKILLS():
    domain_keys = []
    for csv_key, domain_key in SKILL_MAP.items():
        domain_keys.append(domain_key)
        print(f"{csv_key} {domain_key}")

    for skill in SKILLS:
        print(skill)

    assert set(domain_keys) == set(SKILLS)


class TestSkillMapStructure:
    """Test the structure and consistency of skill mappings."""

    def test_skill_map_not_empty(self):
        assert len(SKILL_MAP) > 0

    def test_all_abbreviations_are_two_chars(self):
        for abbr in SKILL_MAP.keys():
            assert len(abbr) == 2, f"Abbreviation '{abbr}' is not 2 characters"

    def test_all_abbreviations_are_uppercase(self):
        for abbr in SKILL_MAP.keys():
            assert abbr.isupper(), f"Abbreviation '{abbr}' is not uppercase"

    def test_all_skill_names_are_lowercase(self):
        for name in SKILL_MAP.values():
            assert (
                name.islower() or "_" in name
            ), f"Skill name '{name}' contains uppercase"

    def test_no_duplicate_abbreviations(self):
        abbrs = list(SKILL_MAP.keys())
        assert len(abbrs) == len(set(abbrs)), "Duplicate abbreviations found"

    def test_no_duplicate_skill_names(self):
        names = list(SKILL_MAP.values())
        assert len(names) == len(set(names)), "Duplicate skill names found"

    def test_skill_abbreviations_is_reverse_of_skill_map(self):
        for abbr, name in SKILL_MAP.items():
            assert SKILL_ABBREVIATIONS[name] == abbr


class TestSkillCategories:
    """Test skill category organization."""

    def test_all_categories_exist(self):
        assert "hitting" in SKILL_CATEGORIES
        assert "defense" in SKILL_CATEGORIES
        assert "pitching" in SKILL_CATEGORIES
        assert "general" in SKILL_CATEGORIES

    def test_every_skill_has_category(self):
        all_categorized = []
        for skills in SKILL_CATEGORIES.values():
            all_categorized.extend(skills)

        for abbr in SKILL_MAP.keys():
            assert abbr in all_categorized, f"Skill '{abbr}' not in any category"

    def test_no_skill_in_multiple_categories(self):
        all_skills = []
        for skills in SKILL_CATEGORIES.values():
            all_skills.extend(skills)

        assert len(all_skills) == len(
            set(all_skills)
        ), "Skill appears in multiple categories"

    def test_hitting_skills_correct(self):
        expected = ["PO", "EY", "CT", "BR", "BU"]
        assert SKILL_CATEGORIES["hitting"] == expected

    def test_defense_skills_correct(self):
        expected = ["CA", "IF", "OF", "AR"]
        assert SKILL_CATEGORIES["defense"] == expected

    def test_pitching_skills_correct(self):
        expected = ["AC", "ST", "RE", "GB", "KK"]
        assert SKILL_CATEGORIES["pitching"] == expected

    def test_general_skills_correct(self):
        expected = ["CL", "SP", "DU"]
        assert SKILL_CATEGORIES["general"] == expected

    def test_clutch_is_general_skill(self):
        """Clutch should be a general skill, not hitting."""
        assert "CL" in SKILL_CATEGORIES["general"]
        assert "CL" not in SKILL_CATEGORIES["hitting"]


class TestSpecificSkills:
    """Test that specific expected skills exist."""

    def test_power_skill_exists(self):
        assert "PO" in SKILL_MAP
        assert SKILL_MAP["PO"] == "power"

    def test_clutch_skill_exists(self):
        assert "CL" in SKILL_MAP
        assert SKILL_MAP["CL"] == "clutch"

    def test_speed_skill_exists(self):
        assert "SP" in SKILL_MAP
        assert SKILL_MAP["SP"] == "speed"

    def test_accuracy_skill_exists(self):
        assert "AC" in SKILL_MAP
        assert SKILL_MAP["AC"] == "accuracy"

    def test_infield_skill_exists(self):
        assert "IF" in SKILL_MAP
        assert SKILL_MAP["IF"] == "infield"


class TestGetSkillName:
    """Test get_skill_name function."""

    def test_get_skill_name_power(self):
        assert get_skill_name("PO") == "power"

    def test_get_skill_name_clutch(self):
        assert get_skill_name("CL") == "clutch"

    def test_get_skill_name_speed(self):
        assert get_skill_name("SP") == "speed"

    def test_get_skill_name_all_skills(self):
        """Test all skills can be retrieved."""
        for abbr, expected_name in SKILL_MAP.items():
            assert get_skill_name(abbr) == expected_name

    def test_get_skill_name_invalid_raises_error(self):
        with pytest.raises(ValueError, match="Unknown skill abbreviation"):
            get_skill_name("XX")

    def test_get_skill_name_error_message_includes_valid_options(self):
        with pytest.raises(ValueError, match="Valid abbreviations"):
            get_skill_name("ZZ")

    def test_get_skill_name_case_sensitive(self):
        """Lowercase abbreviations should fail."""
        with pytest.raises(ValueError):
            get_skill_name("po")


class TestGetSkillAbbr:
    """Test get_skill_abbr function."""

    def test_get_skill_abbr_power(self):
        assert get_skill_abbr("power") == "PO"

    def test_get_skill_abbr_clutch(self):
        assert get_skill_abbr("clutch") == "CL"

    def test_get_skill_abbr_speed(self):
        assert get_skill_abbr("speed") == "SP"

    def test_get_skill_abbr_all_skills(self):
        """Test all skills can be looked up by name."""
        for expected_abbr, name in SKILL_MAP.items():
            assert get_skill_abbr(name) == expected_abbr

    def test_get_skill_abbr_invalid_raises_error(self):
        with pytest.raises(ValueError, match="Unknown skill name"):
            get_skill_abbr("invalid_skill")

    def test_get_skill_abbr_error_message_includes_valid_options(self):
        with pytest.raises(ValueError, match="Valid names"):
            get_skill_abbr("not_a_skill")

    def test_get_skill_abbr_case_sensitive(self):
        """Uppercase skill names should fail."""
        with pytest.raises(ValueError):
            get_skill_abbr("POWER")


class TestIsValidSkill:
    """Test is_valid_skill function."""

    def test_is_valid_skill_power(self):
        assert is_valid_skill("PO") is True

    def test_is_valid_skill_clutch(self):
        assert is_valid_skill("CL") is True

    def test_is_valid_skill_all_valid(self):
        for abbr in SKILL_MAP.keys():
            assert is_valid_skill(abbr) is True

    def test_is_valid_skill_invalid(self):
        assert is_valid_skill("XX") is False

    def test_is_valid_skill_lowercase(self):
        assert is_valid_skill("po") is False

    def test_is_valid_skill_empty_string(self):
        assert is_valid_skill("") is False

    def test_is_valid_skill_too_long(self):
        assert is_valid_skill("POW") is False


class TestIsValidSkillValue:
    """Test is_valid_skill_value function."""

    def test_is_valid_skill_value_min(self):
        assert is_valid_skill_value(SKILL_MIN) is True

    def test_is_valid_skill_value_max(self):
        assert is_valid_skill_value(SKILL_MAX) is True

    def test_is_valid_skill_value_middle(self):
        assert is_valid_skill_value(50) is True

    def test_is_valid_skill_value_zero(self):
        assert is_valid_skill_value(0) is False

    def test_is_valid_skill_value_negative(self):
        assert is_valid_skill_value(-10) is False

    def test_is_valid_skill_value_above_max(self):
        assert is_valid_skill_value(SKILL_MAX + 1) is False

    def test_is_valid_skill_value_below_min(self):
        assert is_valid_skill_value(SKILL_MIN - 1) is False


class TestValidateSkillValue:
    """Test validate_skill_value function."""

    def test_validate_skill_value_valid(self):
        validate_skill_value(50)
        # Should not raise

    def test_validate_skill_value_min(self):
        validate_skill_value(SKILL_MIN)
        # Should not raise

    def test_validate_skill_value_max(self):
        validate_skill_value(SKILL_MAX)
        # Should not raise

    def test_validate_skill_value_zero_raises(self):
        with pytest.raises(ValueError, match="must be between"):
            validate_skill_value(0)

    def test_validate_skill_value_negative_raises(self):
        with pytest.raises(ValueError, match="must be between"):
            validate_skill_value(-5)

    def test_validate_skill_value_above_max_raises(self):
        with pytest.raises(ValueError, match="must be between"):
            validate_skill_value(SKILL_MAX + 1)

    def test_validate_skill_value_with_skill_name_in_error(self):
        with pytest.raises(ValueError, match="'PO'"):
            validate_skill_value(0, "PO")

    def test_validate_skill_value_float_raises_type_error(self):
        with pytest.raises(TypeError, match="must be an integer"):
            validate_skill_value(50.5)

    def test_validate_skill_value_string_raises_type_error(self):
        with pytest.raises(TypeError, match="must be an integer"):
            validate_skill_value("50")


class TestGetSkillsByCategory:
    """Test get_skills_by_category function."""

    def test_get_skills_by_category_hitting(self):
        skills = get_skills_by_category("hitting")
        assert skills == ["PO", "EY", "CT", "BR", "BU"]

    def test_get_skills_by_category_defense(self):
        skills = get_skills_by_category("defense")
        assert skills == ["CA", "IF", "OF", "AR"]

    def test_get_skills_by_category_pitching(self):
        skills = get_skills_by_category("pitching")
        assert skills == ["AC", "ST", "RE", "GB", "KK"]

    def test_get_skills_by_category_general(self):
        skills = get_skills_by_category("general")
        assert skills == ["CL", "SP", "DU"]

    def test_get_skills_by_category_returns_copy(self):
        """Modifying returned list shouldn't affect original."""
        skills = get_skills_by_category("hitting")
        skills.append("XX")
        # Get it again
        skills2 = get_skills_by_category("hitting")
        assert "XX" not in skills2

    def test_get_skills_by_category_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown category"):
            get_skills_by_category("invalid")

    def test_get_skills_by_category_error_shows_valid_categories(self):
        with pytest.raises(ValueError, match="Valid categories"):
            get_skills_by_category("batting")


class TestGetSkillCategory:
    """Test get_skill_category function."""

    def test_get_skill_category_power(self):
        assert get_skill_category("PO") == "hitting"

    def test_get_skill_category_clutch(self):
        assert get_skill_category("CL") == "general"

    def test_get_skill_category_speed(self):
        assert get_skill_category("SP") == "general"

    def test_get_skill_category_infield(self):
        assert get_skill_category("IF") == "defense"

    def test_get_skill_category_accuracy(self):
        assert get_skill_category("AC") == "pitching"

    def test_get_skill_category_all_skills(self):
        """Test all skills return a valid category."""
        valid_categories = set(SKILL_CATEGORIES.keys())
        for abbr in SKILL_MAP.keys():
            category = get_skill_category(abbr)
            assert category in valid_categories

    def test_get_skill_category_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown skill abbreviation"):
            get_skill_category("XX")


class TestGetAllSkills:
    """Test get_all_skills function."""

    def test_get_all_skills_returns_all(self):
        skills = get_all_skills()
        assert len(skills) == len(SKILL_MAP)

    def test_get_all_skills_sorted(self):
        skills = get_all_skills()
        assert skills == sorted(skills)

    def test_get_all_skills_contains_expected(self):
        skills = get_all_skills()
        assert "PO" in skills
        assert "CL" in skills
        assert "SP" in skills
        assert "AC" in skills


class TestFormatSkillDisplay:
    """Test format_skill_display function."""

    def test_format_skill_display_power(self):
        result = format_skill_display("PO", 85)
        assert "Power" in result
        assert "PO" in result
        assert "85" in result

    def test_format_skill_display_clutch(self):
        result = format_skill_display("CL", 70)
        assert "Clutch" in result
        assert "CL" in result
        assert "70" in result

    def test_format_skill_display_base_running(self):
        result = format_skill_display("BR", 90)
        assert "Base Running" in result
        assert "BR" in result
        assert "90" in result

    def test_format_skill_display_ground_balls(self):
        result = format_skill_display("GB", 65)
        assert "Ground Balls" in result
        assert "GB" in result
        assert "65" in result


class TestGetCategoryDisplayName:
    """Test get_category_display_name function."""

    def test_get_category_display_name_hitting(self):
        assert get_category_display_name("hitting") == "Hitting"

    def test_get_category_display_name_defense(self):
        assert get_category_display_name("defense") == "Defense"

    def test_get_category_display_name_with_underscore(self):
        assert get_category_display_name("ground_balls") == "Ground Balls"


class TestConstants:
    """Test module constants."""

    def test_skill_min_is_one(self):
        assert SKILL_MIN == 1

    def test_skill_max_is_hundred(self):
        assert SKILL_MAX == 100

    def test_skill_min_less_than_max(self):
        assert SKILL_MIN < SKILL_MAX

    def test_all_skill_abbrs_set(self):
        assert isinstance(ALL_SKILL_ABBRS, set)
        assert len(ALL_SKILL_ABBRS) == len(SKILL_MAP)

    def test_all_skill_names_set(self):
        assert isinstance(ALL_SKILL_NAMES, set)
        assert len(ALL_SKILL_NAMES) == len(SKILL_MAP)


class TestPositionSkillSets:
    """Test position-specific skill sets."""

    def test_batter_skills_includes_hitting(self):
        for skill in SKILL_CATEGORIES["hitting"]:
            assert skill in BATTER_SKILLS

    def test_batter_skills_includes_general(self):
        for skill in SKILL_CATEGORIES["general"]:
            assert skill in BATTER_SKILLS

    def test_batter_skills_includes_clutch(self):
        """Clutch should be in batter skills (general category)."""
        assert "CL" in BATTER_SKILLS

    def test_pitcher_skills_includes_pitching(self):
        for skill in SKILL_CATEGORIES["pitching"]:
            assert skill in PITCHER_SKILLS

    def test_pitcher_skills_includes_general(self):
        for skill in SKILL_CATEGORIES["general"]:
            assert skill in PITCHER_SKILLS

    def test_pitcher_skills_includes_clutch(self):
        """Clutch should be in pitcher skills (general category)."""
        assert "CL" in PITCHER_SKILLS

    def test_fielder_skills_includes_defense(self):
        for skill in SKILL_CATEGORIES["defense"]:
            assert skill in FIELDER_SKILLS

    def test_fielder_skills_includes_general(self):
        for skill in SKILL_CATEGORIES["general"]:
            assert skill in FIELDER_SKILLS

    def test_fielder_skills_includes_clutch(self):
        """Clutch should be in fielder skills (general category)."""
        assert "CL" in FIELDER_SKILLS


class TestSkillMapIntegrity:
    """Test overall integrity and consistency."""

    def test_expected_skill_count(self):
        """Ensure we have all 17 skills."""
        assert len(SKILL_MAP) == 17

    def test_category_counts(self):
        assert len(SKILL_CATEGORIES["hitting"]) == 5
        assert len(SKILL_CATEGORIES["defense"]) == 4
        assert len(SKILL_CATEGORIES["pitching"]) == 5
        assert len(SKILL_CATEGORIES["general"]) == 3

    def test_roundtrip_abbr_to_name_to_abbr(self):
        """Test that converting back and forth works."""
        for abbr in SKILL_MAP.keys():
            name = get_skill_name(abbr)
            abbr2 = get_skill_abbr(name)
            assert abbr == abbr2

    def test_roundtrip_name_to_abbr_to_name(self):
        """Test that converting back and forth works."""
        for name in SKILL_MAP.values():
            abbr = get_skill_abbr(name)
            name2 = get_skill_name(abbr)
            assert name == name2


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string_abbreviation(self):
        assert is_valid_skill("") is False

    def test_none_abbreviation(self):
        with pytest.raises(ValueError):
            get_skill_name(None)

    def test_numeric_abbreviation(self):
        assert is_valid_skill("12") is False

    def test_special_char_abbreviation(self):
        assert is_valid_skill("P@") is False

    def test_validate_skill_value_boundary_conditions(self):
        # Just below min
        with pytest.raises(ValueError):
            validate_skill_value(0)

        # At min
        validate_skill_value(1)

        # At max
        validate_skill_value(100)

        # Just above max
        with pytest.raises(ValueError):
            validate_skill_value(101)
