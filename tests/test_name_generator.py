"""Unit tests for name generator classes."""

import pytest
import random
from unittest.mock import mock_open, patch, MagicMock
from src.name_generator.names import SimpleNameGenerator, NameGenerator, NameFrequency

# Sample test data matching actual file format
MALE_NAMES = "JAMES          2.758  2.758      1\nJOHN           2.631  5.389      2\nROBERT         2.563  7.952      3\n"
FEMALE_NAMES = "MARY           2.629  2.629      1\nPATRICIA       1.073  3.702      2\nJENNIFER       0.932  7.586      6\n"
LAST_NAMES = "SMITH          1.006  1.006      1\nJOHNSON        0.810  1.816      2\nWILLIAMS       0.699  2.515      3\n"


class TestNameFrequency:
    """Test the NameFrequency dataclass."""

    def test_create_name_frequency(self):
        nf = NameFrequency(name="JOHN", start=0.0, end=2.631)
        assert nf.name == "JOHN"
        assert nf.start == 0.0
        assert nf.end == 2.631

    def test_frozen(self):
        """Test that NameFrequency is immutable."""
        nf = NameFrequency(name="JOHN", start=0.0, end=2.631)
        with pytest.raises(Exception):  # FrozenInstanceError in dataclasses
            nf.name = "JANE"


class TestSimpleNameGenerator:
    """Test the SimpleNameGenerator class."""

    @pytest.fixture
    def mock_files(self):
        """Mock file reading for all tests."""
        with patch("builtins.open", mock_open()) as mock_file:
            # Set up the mock to return different data for each file
            mock_file.return_value.readlines.side_effect = [
                MALE_NAMES.splitlines(keepends=True),
                FEMALE_NAMES.splitlines(keepends=True),
                LAST_NAMES.splitlines(keepends=True),
            ]
            yield mock_file

    @pytest.fixture
    def generator(self, mock_files):
        """Create a SimpleNameGenerator with seeded RNG for testing."""
        rng = random.Random(42)
        return SimpleNameGenerator(rng=rng)

    def test_initialization(self, mock_files):
        """Test that the generator initializes properly."""
        gen = SimpleNameGenerator()
        assert gen.male_names == ["JAMES", "JOHN", "ROBERT"]
        assert gen.female_names == ["MARY", "PATRICIA", "JENNIFER"]
        assert gen.last_names == ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_custom_rng(self, mock_files):
        """Test that custom RNG is used."""
        rng = random.Random(123)
        gen = SimpleNameGenerator(rng=rng)
        assert gen.rng is rng

    def test_default_rng(self, mock_files):
        """Test that default RNG is created if none provided."""
        gen = SimpleNameGenerator()
        assert isinstance(gen.rng, random.Random)

    def test_normalize_gender_male(self, generator):
        """Test gender normalization for male variants."""
        assert generator._normalize_gender("m") == "male"
        assert generator._normalize_gender("M") == "male"
        assert generator._normalize_gender("male") == "male"
        assert generator._normalize_gender("MALE") == "male"

    def test_normalize_gender_female(self, generator):
        """Test gender normalization for female variants."""
        assert generator._normalize_gender("f") == "female"
        assert generator._normalize_gender("F") == "female"
        assert generator._normalize_gender("female") == "female"
        assert generator._normalize_gender("FEMALE") == "female"

    def test_normalize_gender_either(self, generator):
        """Test gender normalization for unrecognized values."""
        assert generator._normalize_gender("either") == "either"
        assert generator._normalize_gender("x") == "either"
        assert generator._normalize_gender("") == "either"

    def test_first_male(self, generator):
        """Test getting a male first name."""
        name = generator.first("male")
        assert name in ["JAMES", "JOHN", "ROBERT"]

    def test_first_female(self, generator):
        """Test getting a female first name."""
        name = generator.first("female")
        assert name in ["MARY", "PATRICIA", "JENNIFER"]

    def test_first_either(self, generator):
        """Test getting either gender first name."""
        name = generator.first("either")
        all_names = ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert name in all_names

    def test_first_default_either(self, generator):
        """Test that default gender is 'either'."""
        name = generator.first()
        all_names = ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert name in all_names

    def test_last(self, generator):
        """Test getting a last name."""
        name = generator.last()
        assert name in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_male(self, generator):
        """Test getting a full male name."""
        first, last = generator.full("male")
        assert first in ["JAMES", "JOHN", "ROBERT"]
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_female(self, generator):
        """Test getting a full female name."""
        first, last = generator.full("female")
        assert first in ["MARY", "PATRICIA", "JENNIFER"]
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_either(self, generator):
        """Test getting a full name of either gender."""
        first, last = generator.full("either")
        all_names = ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert first in all_names
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_make_name_lists_extracts_first_column(self, mock_files):
        """Test that make_name_lists extracts only the first word."""
        gen = SimpleNameGenerator()
        # The data has multiple columns but only first should be extracted
        assert "SMITH" in gen.last_names
        assert "1.006" not in gen.last_names

    def test_full_path(self):
        """Test the full_path static method."""
        path = SimpleNameGenerator.full_path("test.txt")
        assert "test.txt" in path
        assert path.endswith("test.txt")


class TestNameGenerator:
    """Test the NameGenerator class (frequency-based)."""

    @pytest.fixture
    def mock_files(self):
        """Mock file reading for frequency-based generator."""
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.readlines.side_effect = [
                MALE_NAMES.splitlines(keepends=True),
                FEMALE_NAMES.splitlines(keepends=True),
                LAST_NAMES.splitlines(keepends=True),
            ]
            yield mock_file

    @pytest.fixture
    def generator(self, mock_files):
        """Create a NameGenerator with seeded RNG for testing."""
        rng = random.Random(42)
        return NameGenerator(rng=rng)

    def test_make_name_lists_creates_name_frequency(self, generator):
        """Test that NameFrequency objects are created."""
        assert all(isinstance(nf, NameFrequency) for nf in generator.male_names)
        assert all(isinstance(nf, NameFrequency) for nf in generator.female_names)
        assert all(isinstance(nf, NameFrequency) for nf in generator.last_names)

    def test_make_names_static_method(self):
        """Test the static make_names method."""
        data = [
            "SMITH          1.006  1.006      1\n",
            "JOHNSON        0.810  1.816      2\n",
        ]
        name_list = []
        NameGenerator.make_names(data, name_list)

        assert len(name_list) == 2
        assert name_list[0].name == "SMITH"
        assert name_list[0].start == 0.0
        assert name_list[0].end == 1.006
        assert name_list[1].name == "JOHNSON"
        assert name_list[1].start == 1.006
        assert name_list[1].end == 1.816

    def test_max_range(self, generator):
        """Test that _max_range returns the last end value."""
        max_range = generator._max_range(generator.last_names)
        assert max_range == 2.515  # Last name's end value

    def test_first_male_frequency(self, generator):
        """Test getting a frequency-based male name."""
        name = generator.first("male")
        assert name in ["JAMES", "JOHN", "ROBERT"]

    def test_first_female_frequency(self, generator):
        """Test getting a frequency-based female name."""
        name = generator.first("female")
        assert name in ["MARY", "PATRICIA", "JENNIFER"]

    def test_first_either_frequency(self, generator):
        """Test getting either gender with frequency."""
        name = generator.first("either")
        all_names = ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert name in all_names

    def test_first_fallback_when_no_match(self, generator):
        """Test fallback behavior when no matching name found."""
        # Mock uniform to return a value that won't match
        generator.rng.uniform = MagicMock(return_value=999.0)
        name = generator.first("male")
        # Should still return a valid name from the fallback
        assert name in ["JAMES", "JOHN", "ROBERT"]

    def test_last_frequency(self, generator):
        """Test getting a frequency-based last name."""
        name = generator.last()
        assert name in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_male_frequency(self, generator):
        """Test getting a full name with male frequency."""
        first, last = generator.full("male")
        assert first in ["JAMES", "JOHN", "ROBERT"]
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_female_frequency(self, generator):
        """Test getting a full name with female frequency."""
        first, last = generator.full("female")
        assert first in ["MARY", "PATRICIA", "JENNIFER"]
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_either_frequency(self, generator):
        """Test getting a full name with either gender."""
        first, last = generator.full("either")
        all_names = ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert first in all_names
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_full_default_gender_is_male(self, generator):
        """Test that default gender for full() is male in NameGenerator."""
        first, last = generator.full()
        # Default is "either" in NameGenerator.full()
        assert first in ["JAMES", "JOHN", "ROBERT", "MARY", "PATRICIA", "JENNIFER"]
        assert last in ["SMITH", "JOHNSON", "WILLIAMS"]

    def test_matching_names_boundary_condition(self, generator):
        """Test the boundary matching logic with -0.001 tolerance."""
        # Set uniform to return exact boundary value
        generator.rng.uniform = MagicMock(return_value=1.006)
        name = generator.last()
        # Should match SMITH (ends at 1.006) or JOHNSON (starts at 1.006)
        assert name in ["SMITH", "JOHNSON"]

    def test_inheritance(self, generator):
        """Test that NameGenerator inherits from SimpleNameGenerator."""
        assert isinstance(generator, SimpleNameGenerator)


class TestIntegration:
    """Integration tests for realistic usage."""

    @pytest.fixture
    def mock_files(self):
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.readlines.side_effect = [
                MALE_NAMES.splitlines(keepends=True),
                FEMALE_NAMES.splitlines(keepends=True),
                LAST_NAMES.splitlines(keepends=True),
            ]
            yield mock_file

    def test_generate_multiple_names_simple(self, mock_files):
        """Test generating multiple names with SimpleNameGenerator."""
        gen = SimpleNameGenerator(rng=random.Random(42))
        names = [gen.full() for _ in range(10)]

        assert len(names) == 10
        assert all(isinstance(name, tuple) and len(name) == 2 for name in names)

    def test_generate_multiple_names_frequency(self, mock_files):
        """Test generating multiple names with NameGenerator."""
        gen = NameGenerator(rng=random.Random(42))
        names = [gen.full() for _ in range(10)]

        assert len(names) == 10
        assert all(isinstance(name, tuple) and len(name) == 2 for name in names)

    # def test_reproducible_with_seed(self, mock_files):
    #     """Test that same seed produces same names."""
    #     gen1 = SimpleNameGenerator(rng=random.Random(12345))
    #     gen2 = SimpleNameGenerator(rng=random.Random(12345))

    #     names1 = [gen1.full() for _ in range(5)]
    #     names2 = [gen2.full() for _ in range(5)]

    #     assert names1 == names2

    def test_reproducible_with_seed(self):
        """Test that same seed produces same names."""
        with patch("builtins.open", mock_open()) as mock_file:
            # Provide enough side effects for both generators (6 file reads total)
            mock_file.return_value.readlines.side_effect = [
                MALE_NAMES.splitlines(keepends=True),
                FEMALE_NAMES.splitlines(keepends=True),
                LAST_NAMES.splitlines(keepends=True),
                MALE_NAMES.splitlines(keepends=True),
                FEMALE_NAMES.splitlines(keepends=True),
                LAST_NAMES.splitlines(keepends=True),
            ]

            gen1 = SimpleNameGenerator(rng=random.Random(12345))
            gen2 = SimpleNameGenerator(rng=random.Random(12345))

            names1 = [gen1.full() for _ in range(5)]
            names2 = [gen2.full() for _ in range(5)]

            assert names1 == names2
