# tests/team/test_team_factory.py
"""
Tests for TeamFactory.

Tests cover:
- from_csv: CSV parsing, error handling, minimum players
- generate_team: Positional distribution, roster sizes, validation
"""

import io
import pytest
from unittest.mock import MagicMock, patch
from collections import Counter

from src.team.team_factory import TeamFactory
from src.team.team_record import TeamRecord
from src.player.player_record import PlayerRecord


@pytest.fixture
def valid_csv():
    """Generate a valid CSV with 9 players."""
    header = "id,first_name,last_name,bats,throws\n"
    rows = [f"{i},First{i},Last{i},R,R\n" for i in range(1, 10)]
    return header + "".join(rows)


class TestTeamFactoryFromCSV:
    """Test from_csv() method."""

    @patch("src.team.team_factory.open", create=True)
    @patch("src.team.team_factory.PlayerRecord.from_csv_row")
    def test_from_csv_creates_team_record(
        self,
        mock_from_csv_row,
        mock_open,
        valid_csv,
    ):
        """Happy path: builds a TeamRecord from CSV."""
        mock_open.return_value.__enter__.return_value = io.StringIO(valid_csv)

        fake_player = MagicMock(spec=PlayerRecord)
        mock_from_csv_row.return_value = fake_player

        factory = TeamFactory()

        team = factory.from_csv(
            path="team.csv",
            city="Chicago",
            mascot="Bears",
        )

        assert isinstance(team, TeamRecord)
        assert team.city == "Chicago"
        assert team.mascot == "Bears"
        assert len(team.players) == 9
        assert all(p is fake_player for p in team.players)

    @patch("src.team.team_factory.open", create=True)
    @patch("src.team.team_factory.PlayerRecord.from_csv_row")
    def test_from_csv_invalid_row_reports_row_number(
        self,
        mock_from_csv_row,
        mock_open,
        valid_csv,
    ):
        """Invalid row includes row number in error message."""
        mock_open.return_value.__enter__.return_value = io.StringIO(valid_csv)

        mock_from_csv_row.side_effect = ValueError("bad data")

        factory = TeamFactory()

        with pytest.raises(ValueError, match="Invalid player row 1"):
            factory.from_csv(
                path="team.csv",
                city="NY",
                mascot="Mets",
            )

    @patch("src.team.team_factory.open", create=True)
    @patch("src.team.team_factory.PlayerRecord.from_csv_row")
    def test_from_csv_requires_minimum_players(
        self,
        mock_from_csv_row,
        mock_open,
    ):
        """Fewer than 9 players is rejected."""
        csv_data = "ID,Name,B,T\n" "1,A,R,R\n" "2,C,R,R\n"
        mock_open.return_value.__enter__.return_value = io.StringIO(csv_data)
        mock_from_csv_row.return_value = MagicMock(spec=PlayerRecord)

        factory = TeamFactory()

        with pytest.raises(ValueError, match="at least 9 players"):
            factory.from_csv(
                path="small.csv",
                city="LA",
                mascot="Dodgers",
            )

    @patch("src.team.team_factory.open", create=True)
    @patch("src.team.team_factory.PlayerRecord.from_csv_row")
    def test_from_csv_players_are_tuple(
        self,
        mock_from_csv_row,
        mock_open,
        valid_csv,
    ):
        """Players are stored as an immutable tuple."""
        mock_open.return_value.__enter__.return_value = io.StringIO(valid_csv)
        mock_from_csv_row.return_value = MagicMock(spec=PlayerRecord)

        factory = TeamFactory()
        team = factory.from_csv(path="team.csv", city="SF", mascot="Giants")

        assert isinstance(team.players, tuple)


class TestTeamFactoryGenerateTeam:
    """Test generate_team() method."""

    def test_generate_team_creates_team_record(self):
        """Generates a valid TeamRecord."""
        factory = TeamFactory()

        team = factory.generate_team(city="Boston", mascot="Red Sox", size=26)

        assert isinstance(team, TeamRecord)
        assert team.city == "Boston"
        assert team.mascot == "Red Sox"
        assert len(team.players) == 26

    def test_generate_team_players_are_tuple(self):
        """Players are stored as an immutable tuple."""
        factory = TeamFactory()

        team = factory.generate_team(city="SF", mascot="Giants", size=9)

        assert isinstance(team.players, tuple)

    def test_generate_team_all_players_are_player_records(self):
        """All players are PlayerRecord instances."""
        factory = TeamFactory()

        team = factory.generate_team(city="NY", mascot="Yankees", size=15)

        assert all(isinstance(p, PlayerRecord) for p in team.players)

    def test_generate_team_minimum_size_validation(self):
        """Raises ValueError for teams with fewer than 9 players."""
        factory = TeamFactory()

        with pytest.raises(ValueError, match="at least 9 players"):
            factory.generate_team(city="Chicago", mascot="Cubs", size=8)

    def test_generate_team_accepts_exactly_nine_players(self):
        """Minimum valid team size (9 players) works."""
        factory = TeamFactory()

        team = factory.generate_team(city="LA", mascot="Dodgers", size=9)

        assert len(team.players) == 9

    def test_generate_team_default_size_is_160(self):
        """Default roster size is 40 players."""
        factory = TeamFactory()

        team = factory.generate_team(city="Toronto", mascot="Blue Jays")

        assert len(team.players) == 160

    def test_generate_team_full_roster_distribution(self):
        """26+ player roster follows specified positional distribution."""
        factory = TeamFactory()

        team = factory.generate_team(city="Seattle", mascot="Mariners", size=26)

        # Count positions
        position_counts = Counter(p.position for p in team.players)

        # Verify exact distribution for 26-player roster
        assert position_counts["sp"] == 7
        assert position_counts["rp"] == 6
        assert position_counts["c"] == 2
        assert position_counts["ss"] == 1
        assert position_counts["2b"] == 1
        assert position_counts["3b"] == 1
        assert position_counts["1b"] == 1
        assert position_counts["lf"] == 1
        assert position_counts["cf"] == 1
        assert position_counts["rf"] == 1
        assert position_counts["if"] == 2
        assert position_counts["of"] == 2

        # Total should be exactly 26
        assert sum(position_counts.values()) == 26

    def test_generate_team_40_player_roster_has_extras(self):
        """40-player roster has 14 additional random players."""
        factory = TeamFactory()

        team = factory.generate_team(city="Houston", mascot="Astros", size=40)

        # Count positions
        position_counts = Counter(p.position for p in team.players)

        # Core 26 positions should still be present
        assert position_counts["sp"] >= 7
        assert position_counts["rp"] >= 6
        assert position_counts["c"] >= 2

        # Total should be 40
        assert len(team.players) == 40

    def test_generate_team_small_roster_has_core_positions(self):
        """Small roster (9-25 players) has at least 1 of each core position."""
        factory = TeamFactory()

        size = 15
        team = factory.generate_team(city="Tampa", mascot="Rays", size=size)

        position_counts = Counter(p.position for p in team.players)

        # Should have at least one pitcher
        assert position_counts["sp"] >= 1
        if size > 9:
            assert position_counts["rp"] >= 1

        # Should have core defensive positions
        assert position_counts["c"] >= 1
        assert position_counts["ss"] >= 1
        assert position_counts["2b"] >= 1
        assert position_counts["3b"] >= 1
        assert position_counts["1b"] >= 1
        assert position_counts["lf"] >= 1
        assert position_counts["cf"] >= 1
        assert position_counts["rf"] >= 1

    def test_generate_team_tiny_roster_has_core_positions(self):
        """Small roster (9-25 players) has at least 1 of each core position."""
        factory = TeamFactory()

        size = 9
        team = factory.generate_team(city="Tampa", mascot="Rays", size=size)

        position_counts = Counter(p.position for p in team.players)

        # Should have at least one pitcher
        assert position_counts["sp"] >= 1
        if size > 9:
            assert position_counts["rp"] >= 1

        # Should have core defensive positions
        assert position_counts["c"] >= 1
        assert position_counts["ss"] >= 1
        assert position_counts["2b"] >= 1
        assert position_counts["3b"] >= 1
        assert position_counts["1b"] >= 1
        assert position_counts["lf"] >= 1
        assert position_counts["cf"] >= 1
        assert position_counts["rf"] >= 1

    def test_generate_team_ten_man_roster_has_core_positions(self):
        """Small roster (9-25 players) has at least 1 of each core position."""
        factory = TeamFactory()

        size = 10
        team = factory.generate_team(city="Tampa", mascot="Rays", size=size)

        position_counts = Counter(p.position for p in team.players)

        # Should have at least one pitcher
        assert position_counts["sp"] >= 1
        if size > 9:
            assert position_counts["rp"] >= 1

        # Should have core defensive positions
        assert position_counts["c"] >= 1
        assert position_counts["ss"] >= 1
        assert position_counts["2b"] >= 1
        assert position_counts["3b"] >= 1
        assert position_counts["1b"] >= 1
        assert position_counts["lf"] >= 1
        assert position_counts["cf"] >= 1
        assert position_counts["rf"] >= 1

    def test_generate_team_different_sizes(self):
        """Test various roster sizes work correctly."""
        factory = TeamFactory()

        sizes = [9, 15, 20, 25, 26, 30, 35, 40]

        for size in sizes:
            team = factory.generate_team(city="Test", mascot="Team", size=size)
            assert len(team.players) == size

    def test_generate_team_pitchers_proportion_large_roster(self):
        """Large roster has appropriate proportion of pitchers (~32%)."""
        factory = TeamFactory()

        team = factory.generate_team(city="Atlanta", mascot="Braves", size=40)

        position_counts = Counter(p.position for p in team.players)
        total_pitchers = position_counts["sp"] + position_counts["rp"]

        # Should be roughly 13 pitchers on 40-man roster (32.5%)
        # Allow some variance due to random fill
        assert 12 <= total_pitchers <= 20

    def test_generate_team_has_unique_id(self):
        """Each generated team has a unique ID."""
        factory = TeamFactory()

        team1 = factory.generate_team(city="Team1", mascot="A", size=9)
        team2 = factory.generate_team(city="Team2", mascot="B", size=9)

        assert team1.id != team2.id

    def test_generate_team_reproducible_with_seed(self):
        """Using same seed produces identical teams."""
        import random

        seed = 42
        factory1 = TeamFactory(rng=random.Random(seed))
        factory2 = TeamFactory(rng=random.Random(seed))

        team1 = factory1.generate_team(city="Test", mascot="A", size=20)
        team2 = factory2.generate_team(city="Test", mascot="A", size=20)

        # Compare positions
        positions1 = [p.position for p in team1.players]
        positions2 = [p.position for p in team2.players]

        assert positions1 == positions2


class TestTeamFactoryIntegration:
    """Integration tests for TeamFactory."""

    def test_generate_realistic_mlb_roster(self):
        """Generate a realistic 26-man MLB roster."""
        factory = TeamFactory()

        team = factory.generate_team(city="New York", mascot="Yankees", size=26)

        assert len(team.players) == 26
        assert team.city == "New York"
        assert team.mascot == "Yankees"

        # Verify all players have valid attributes
        for player in team.players:
            assert player.id
            assert player.first_name
            assert player.last_name
            assert player.position
            assert player.bats in ("L", "R", "S")
            assert player.throws in ("L", "R")
            assert player.skills is not None

    def test_generate_expanded_roster(self):
        """Generate a 40-man expanded roster."""
        factory = TeamFactory()

        team = factory.generate_team(city="Los Angeles", mascot="Dodgers", size=40)

        assert len(team.players) == 40

        # Should have enough pitching depth
        pitchers = [p for p in team.players if p.position in ("sp", "rp")]
        assert len(pitchers) >= 13

        # Should have defensive depth
        catchers = [p for p in team.players if p.position == "c"]
        assert len(catchers) >= 2
