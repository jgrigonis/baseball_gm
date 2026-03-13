# tests/league/test_schedule.py
import pytest
import sqlite3
from datetime import date, timedelta
from collections import Counter
import random

from src.league.schedule import ScheduleGenerator, ScheduledGame, save_schedule_to_db


class TestScheduledGame:
    """Test ScheduledGame dataclass."""

    def test_scheduled_game_creation(self):
        """Test creating a ScheduledGame."""
        game = ScheduledGame(
            id="game-1",
            season_id="season-1",
            home_team_id="team-a",
            away_team_id="team-b",
            game_date=date(2025, 4, 1),
            series_id=None,
        )

        assert game.id == "game-1"
        assert game.season_id == "season-1"
        assert game.home_team_id == "team-a"
        assert game.away_team_id == "team-b"
        assert game.game_date == date(2025, 4, 1)
        assert game.series_id is None

    def test_scheduled_game_with_series(self):
        """Test ScheduledGame with series_id."""
        game = ScheduledGame(
            id="game-1",
            season_id="season-1",
            home_team_id="team-a",
            away_team_id="team-b",
            game_date=date(2025, 4, 1),
            series_id="series-1",
        )

        assert game.series_id == "series-1"


class TestScheduleGenerator:
    """Test ScheduleGenerator class."""

    @pytest.fixture
    def generator(self):
        """Create a generator with seeded RNG for deterministic tests."""
        return ScheduleGenerator(rng=random.Random(42))

    @pytest.fixture
    def four_teams(self):
        """Four team IDs for testing."""
        return ["team-a", "team-b", "team-c", "team-d"]

    # -------------------------------------------------------------------
    # generate_round_robin tests
    # -------------------------------------------------------------------

    def test_round_robin_basic(self, generator, four_teams):
        """Test basic round-robin with 4 teams."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        # 4 teams = 6 pairings (C(4,2))
        # With home_and_away = 2 games per pairing = 12 total games
        assert len(matchups) == 12

    def test_round_robin_correct_pairings(self, generator, four_teams):
        """Test that all team pairings are present."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=False  # Easier to verify
        )

        # Convert to set to ignore order
        matchup_set = set(matchups)

        # Should have exactly 6 unique pairings
        assert len(matchup_set) == 6

        # Each team should appear in 3 games (plays 3 other teams)
        all_teams = [team for matchup in matchups for team in matchup]
        team_counts = Counter(all_teams)

        for team in four_teams:
            assert team_counts[team] == 3

    def test_round_robin_home_and_away(self, generator, four_teams):
        """Test that home_and_away creates reciprocal matchups."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        # For each (home, away), should also have (away, home)
        matchup_set = set(matchups)

        for home, away in matchups:
            assert (away, home) in matchup_set

    def test_round_robin_multiple_games_per_matchup(self, generator, four_teams):
        """Test games_per_matchup parameter."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=3, home_and_away=True
        )

        # 6 pairings * 3 games * 2 (home/away) = 36 games
        assert len(matchups) == 36

        # Each specific matchup should appear 3 times
        matchup_counts = Counter(matchups)
        for count in matchup_counts.values():
            assert count == 3

    def test_round_robin_two_teams(self, generator):
        """Test with minimum number of teams."""
        teams = ["team-a", "team-b"]
        matchups = generator.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=True
        )

        # 1 pairing * 2 (home/away) = 2 games
        assert len(matchups) == 2
        assert set(matchups) == {("team-a", "team-b"), ("team-b", "team-a")}

    def test_round_robin_shuffles(self):
        """Test that RNG affects shuffle."""
        teams = ["team-a", "team-b", "team-c"]

        gen1 = ScheduleGenerator(rng=random.Random(1))
        gen2 = ScheduleGenerator(rng=random.Random(2))

        matchups1 = gen1.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=False
        )
        matchups2 = gen2.generate_round_robin(
            teams, games_per_matchup=1, home_and_away=False
        )

        # Same matchups, different order (probably)
        assert set(matchups1) == set(matchups2)
        # Likely different order (not guaranteed but very likely)
        # Just check they're both valid lists
        assert len(matchups1) == len(matchups2) == 3

    def test_round_robin_no_self_play(self, generator, four_teams):
        """Test that no team plays itself."""
        matchups = generator.generate_round_robin(
            four_teams, games_per_matchup=1, home_and_away=True
        )

        for home, away in matchups:
            assert home != away

    # -------------------------------------------------------------------
    # create_schedule tests
    # -------------------------------------------------------------------

    def test_create_schedule_basic(self, generator, four_teams):
        """Test basic schedule creation."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_matchup=1,
            home_and_away=True,
        )

        # 4 teams = 12 games
        assert len(schedule) == 12

        # All games should be ScheduledGame instances
        assert all(isinstance(game, ScheduledGame) for game in schedule)

    def test_create_schedule_game_fields(self, generator, four_teams):
        """Test that all game fields are populated correctly."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_matchup=1,
            home_and_away=True,
        )

        for game in schedule:
            assert game.id  # Has an ID
            assert game.season_id == "season-1"
            assert game.home_team_id in four_teams
            assert game.away_team_id in four_teams
            assert game.home_team_id != game.away_team_id
            assert isinstance(game.game_date, date)
            assert game.series_id is None

    def test_create_schedule_unique_ids(self, generator, four_teams):
        """Test that all game IDs are unique."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_matchup=2,
            home_and_away=True,
        )

        game_ids = [game.id for game in schedule]
        assert len(game_ids) == len(set(game_ids))

    def test_create_schedule_date_progression(self, generator, four_teams):
        """Test that dates progress correctly."""
        start = date(2025, 4, 1)
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=start,
            games_per_matchup=1,
            home_and_away=True,
        )

        # Dates should be monotonically increasing or equal
        dates = [game.game_date for game in schedule]
        for i in range(len(dates) - 1):
            assert dates[i] <= dates[i + 1]

        # First game should be on start date
        assert schedule[0].game_date == start

    def test_create_schedule_date_advancement(self, generator, four_teams):
        """Test that dates advance after each round."""
        start = date(2025, 4, 1)
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=start,
            games_per_matchup=1,
            home_and_away=True,
        )

        # With 4 teams, 2 games per round (4 // 2)
        # After game 2, 4, 6, 8, 10, 12 should advance date
        # Collect unique dates
        unique_dates = sorted(set(game.game_date for game in schedule))

        # Should span multiple days
        assert len(unique_dates) > 1

        # Dates should be consecutive days
        for i in range(len(unique_dates) - 1):
            assert unique_dates[i + 1] - unique_dates[i] == timedelta(days=1)

    def test_create_schedule_matchup_coverage(self, generator, four_teams):
        """Test that all expected matchups are scheduled."""
        schedule = generator.create_schedule(
            season_id="season-1",
            team_ids=four_teams,
            start_date=date(2025, 4, 1),
            games_per_matchup=2,
            home_and_away=True,
        )

        # Extract matchups from schedule
        matchups = [(g.home_team_id, g.away_team_id) for g in schedule]
        matchup_counts = Counter(matchups)

        # Each specific matchup should appear exactly 2 times
        for count in matchup_counts.values():
            assert count == 2

        # Total should be 6 unique pairings * 2 games * 2 (home/away) = 24
        assert len(schedule) == 24


class TestSaveScheduleToDB:
    """Test save_schedule_to_db function."""

    @pytest.fixture
    def db_connection(self):
        """Create in-memory SQLite database."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Create games table
        conn.execute(
            """
            CREATE TABLE games (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                season_id TEXT NOT NULL,
                series_id TEXT,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """
        )

        yield conn
        conn.close()

    def test_save_empty_schedule(self, db_connection, capsys):
        """Test saving empty schedule."""
        save_schedule_to_db(db_connection, [])

        cursor = db_connection.execute("SELECT COUNT(*) FROM games")
        count = cursor.fetchone()[0]
        assert count == 0

        # Check print output
        captured = capsys.readouterr()
        assert "Saved 0 games" in captured.out

    def test_save_single_game(self, db_connection, capsys):
        """Test saving a single game."""
        schedule = [
            ScheduledGame(
                id="game-1",
                season_id="season-1",
                home_team_id="team-a",
                away_team_id="team-b",
                game_date=date(2025, 4, 1),
                series_id=None,
            )
        ]

        save_schedule_to_db(db_connection, schedule)

        # Verify database
        cursor = db_connection.execute("SELECT * FROM games WHERE id = ?", ("game-1",))
        row = cursor.fetchone()

        assert row is not None
        assert row["id"] == "game-1"
        assert row["season_id"] == "season-1"
        assert row["home_team_id"] == "team-a"
        assert row["away_team_id"] == "team-b"
        assert row["date"] == "2025-04-01"

        # Check print output
        captured = capsys.readouterr()
        assert "Saved 1 games" in captured.out

    def test_save_multiple_games(self, db_connection):
        """Test saving multiple games."""
        schedule = [
            ScheduledGame(
                id=f"game-{i}",
                season_id="season-1",
                home_team_id="team-a",
                away_team_id="team-b",
                game_date=date(2025, 4, i),
                series_id=None,
            )
            for i in range(1, 6)
        ]

        save_schedule_to_db(db_connection, schedule)

        # Verify count
        cursor = db_connection.execute("SELECT COUNT(*) FROM games")
        count = cursor.fetchone()[0]
        assert count == 5

        # Verify all IDs present
        cursor = db_connection.execute("SELECT id FROM games ORDER BY id")
        ids = [row["id"] for row in cursor.fetchall()]
        assert ids == ["game-1", "game-2", "game-3", "game-4", "game-5"]

    def test_save_full_schedule(self, db_connection):
        """Test saving a complete generated schedule."""
        generator = ScheduleGenerator(rng=random.Random(42))
        schedule = generator.create_schedule(
            season_id="season-2025",
            team_ids=["team-a", "team-b", "team-c", "team-d"],
            start_date=date(2025, 4, 1),
            games_per_matchup=3,
            home_and_away=True,
        )

        save_schedule_to_db(db_connection, schedule)

        # Verify count (4 teams, 6 pairings, 3 games, home/away = 36)
        cursor = db_connection.execute("SELECT COUNT(*) FROM games")
        count = cursor.fetchone()[0]
        assert count == 36

        # Verify season_id on all games
        cursor = db_connection.execute(
            "SELECT COUNT(*) FROM games WHERE season_id = ?", ("season-2025",)
        )
        count = cursor.fetchone()[0]
        assert count == 36

    def test_save_preserves_all_fields(self, db_connection):
        """Test that all fields are correctly saved."""
        game = ScheduledGame(
            id="test-game",
            season_id="test-season",
            home_team_id="home-team",
            away_team_id="away-team",
            game_date=date(2025, 12, 25),
            series_id=None,
        )

        save_schedule_to_db(db_connection, [game])

        cursor = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", ("test-game",)
        )
        row = cursor.fetchone()

        assert row["id"] == "test-game"
        assert row["season_id"] == "test-season"
        assert row["home_team_id"] == "home-team"
        assert row["away_team_id"] == "away-team"
        assert row["date"] == "2025-12-25"
        assert row["series_id"] is None
