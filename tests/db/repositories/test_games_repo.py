# tests/db/repositories/test_games_repo.py
import pytest
import sqlite3

from src.db.repositories.games_repo import GameRepository
from src.game.game import GameResult


@pytest.fixture
def db_connection():
    """Create in-memory SQLite database with games table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

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
            home_score INTEGER,
            away_score INTEGER,
            winner_id TEXT,
            innings_played INTEGER,
            completed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        )
    """
    )

    yield conn
    conn.close()


@pytest.fixture
def game_repo(db_connection):
    """Create GameRepository instance."""
    return GameRepository(db_connection)


@pytest.fixture
def sample_game(db_connection):
    """Insert a sample game into database."""
    db_connection.execute(
        """
        INSERT INTO games (id, date, season_id, home_team_id, away_team_id, completed)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("game-1", "2025-04-01", "season-1", "team-home", "team-away", 0),
    )
    db_connection.commit()
    return "game-1"


@pytest.fixture
def completed_game(db_connection):
    """Insert a completed game into database."""
    db_connection.execute(
        """
        INSERT INTO games (
            id, date, season_id, home_team_id, away_team_id, 
            home_score, away_score, winner_id, innings_played, completed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "game-2",
            "2025-04-02",
            "season-1",
            "team-home",
            "team-away",
            5,
            3,
            "team-home",
            9,
            1,
        ),
    )
    db_connection.commit()
    return "game-2"


class TestGameRepositoryGet:
    """Test get() method."""

    def test_get_existing_game(self, game_repo, sample_game):
        """Test getting an existing game."""
        result = game_repo.get(sample_game)

        assert result is not None
        assert result["game_id"] == "game-1"
        assert result["season_id"] == "season-1"
        assert result["home_team_id"] == "team-home"
        assert result["away_team_id"] == "team-away"
        assert result["game_date"] == "2025-04-01"
        assert result["completed"] == 0
        assert result["home_score"] is None
        assert result["away_score"] is None
        assert result["winner_id"] is None
        assert result["innings_played"] is None

    def test_get_completed_game(self, game_repo, completed_game):
        """Test getting a completed game with scores."""
        result = game_repo.get(completed_game)

        assert result is not None
        assert result["game_id"] == "game-2"
        assert result["completed"] == 1
        assert result["home_score"] == 5
        assert result["away_score"] == 3
        assert result["winner_id"] == "team-home"
        assert result["innings_played"] == 9

    def test_get_nonexistent_game(self, game_repo):
        """Test getting a game that doesn't exist."""
        result = game_repo.get("nonexistent-game")

        assert result is None

    def test_get_returns_all_fields(self, game_repo, sample_game):
        """Test that get returns all expected fields."""
        result = game_repo.get(sample_game)

        expected_fields = {
            "game_id",
            "season_id",
            "series_id",
            "home_team_id",
            "away_team_id",
            "game_date",
            "completed",
            "home_score",
            "away_score",
            "winner_id",
            "innings_played",
        }

        assert set(result.keys()) == expected_fields


class TestGameRepositorySaveResult:
    """Test save_result() method."""

    def test_save_result_basic(self, game_repo, sample_game, db_connection):
        """Test saving a game result."""
        result = GameResult(
            home_team="Home Team",
            away_team="Away Team",
            home_score=5,
            away_score=3,
            innings_played=9,
            winner="Home Team",
            winning_margin=2,
        )

        game_repo.save_result(sample_game, result, "team-home")

        # Verify database was updated
        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (sample_game,)
        ).fetchone()

        assert row["home_score"] == 5
        assert row["away_score"] == 3
        assert row["winner_id"] == "team-home"
        assert row["innings_played"] == 9
        assert row["completed"] == 1

    def test_save_result_extra_innings(self, game_repo, sample_game, db_connection):
        """Test saving a game that went to extra innings."""
        result = GameResult(
            home_team="Home Team",
            away_team="Away Team",
            home_score=4,
            away_score=3,
            innings_played=12,
            winner="Home Team",
            winning_margin=1,
        )

        game_repo.save_result(sample_game, result, "team-home")

        row = db_connection.execute(
            "SELECT innings_played FROM games WHERE id = ?", (sample_game,)
        ).fetchone()

        assert row["innings_played"] == 12

    def test_save_result_marks_completed(self, game_repo, sample_game, db_connection):
        """Test that save_result marks game as completed."""
        result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=1,
            away_score=0,
            innings_played=9,
            winner="Home",
            winning_margin=1,
        )

        # Verify initially not completed
        row = db_connection.execute(
            "SELECT completed FROM games WHERE id = ?", (sample_game,)
        ).fetchone()
        assert row["completed"] == 0

        game_repo.save_result(sample_game, result, "team-home")

        # Verify now completed
        row = db_connection.execute(
            "SELECT completed FROM games WHERE id = ?", (sample_game,)
        ).fetchone()
        assert row["completed"] == 1

    def test_save_result_overwrites_existing(
        self, game_repo, completed_game, db_connection
    ):
        """Test that save_result can overwrite an existing result."""
        new_result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=10,
            away_score=8,
            innings_played=11,
            winner="Home",
            winning_margin=2,
        )

        game_repo.save_result(completed_game, new_result, "team-home")

        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (completed_game,)
        ).fetchone()

        assert row["home_score"] == 10
        assert row["away_score"] == 8
        assert row["innings_played"] == 11


class TestGameRepositoryGetSeasonGames:
    """Test get_season_games() method."""

    @pytest.fixture
    def season_games(self, db_connection):
        """Create multiple games for a season."""
        games = [
            ("game-s1-1", "2025-04-01", "season-1", "home-1", "away-1", 0, None, None),
            ("game-s1-2", "2025-04-02", "season-1", "home-2", "away-2", 1, 5, 3),
            ("game-s1-3", "2025-04-03", "season-1", "home-3", "away-3", 1, 2, 1),
            ("game-s1-4", "2025-04-04", "season-1", "home-4", "away-4", 0, None, None),
            ("game-s2-1", "2025-04-01", "season-2", "home-5", "away-5", 1, 4, 2),
        ]

        for game in games:
            db_connection.execute(
                """
                INSERT INTO games (
                    id, date, season_id, home_team_id, away_team_id, 
                    completed, home_score, away_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                game,
            )

        db_connection.commit()

    def test_get_all_season_games(self, game_repo, season_games):
        """Test getting all games for a season."""
        games = game_repo.get_season_games("season-1")

        assert len(games) == 4
        assert all(g["season_id"] == "season-1" for g in games)

    def test_get_season_games_ordered_by_date(self, game_repo, season_games):
        """Test that games are ordered by date."""
        games = game_repo.get_season_games("season-1")

        dates = [g["game_date"] for g in games]
        assert dates == sorted(dates)

    def test_get_completed_games_only(self, game_repo, season_games):
        """Test getting only completed games."""
        games = game_repo.get_season_games("season-1", completed_only=True)

        assert len(games) == 2
        assert all(g["completed"] == 1 for g in games)
        assert set(g["game_id"] for g in games) == {"game-s1-2", "game-s1-3"}

    def test_get_incomplete_games_only(self, game_repo, season_games):
        """Test getting only incomplete games."""
        games = game_repo.get_season_games("season-1", incomplete_only=True)

        assert len(games) == 2
        assert all(g["completed"] in (0, None) for g in games)
        assert set(g["game_id"] for g in games) == {"game-s1-1", "game-s1-4"}

    def test_get_games_different_season(self, game_repo, season_games):
        """Test getting games for a different season."""
        games = game_repo.get_season_games("season-2")

        assert len(games) == 1
        assert games[0]["game_id"] == "game-s2-1"

    def test_get_season_games_empty(self, game_repo):
        """Test getting games for a season with no games."""
        games = game_repo.get_season_games("nonexistent-season")

        assert games == []

    def test_get_season_games_returns_all_fields(self, game_repo, season_games):
        """Test that all fields are returned."""
        games = game_repo.get_season_games("season-1")

        expected_fields = {
            "game_id",
            "season_id",
            "home_team_id",
            "away_team_id",
            "game_date",
            "completed",
            "home_score",
            "away_score",
            "winner_id",
            "innings_played",
        }

        for game in games:
            assert set(game.keys()) == expected_fields


class TestGameRepositoryClearResult:
    """Test clear_result() method."""

    def test_clear_result_completed_game(
        self, game_repo, completed_game, db_connection
    ):
        """Test clearing a completed game result."""
        # Verify game is initially completed
        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (completed_game,)
        ).fetchone()
        assert row["completed"] == 1
        assert row["home_score"] == 5

        # Clear the result
        game_repo.clear_result(completed_game)

        # Verify fields are cleared
        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (completed_game,)
        ).fetchone()

        assert row["completed"] == 0
        assert row["home_score"] is None
        assert row["away_score"] is None
        assert row["winner_id"] is None
        assert row["innings_played"] is None

    def test_clear_result_preserves_game_info(
        self, game_repo, completed_game, db_connection
    ):
        """Test that clearing result preserves game identity info."""
        game_repo.clear_result(completed_game)

        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (completed_game,)
        ).fetchone()

        # These should not be affected
        assert row["id"] == "game-2"
        assert row["season_id"] == "season-1"
        assert row["home_team_id"] == "team-home"
        assert row["away_team_id"] == "team-away"
        assert row["date"] == "2025-04-02"

    def test_clear_result_incomplete_game(self, game_repo, sample_game, db_connection):
        """Test clearing an already incomplete game (no-op)."""
        game_repo.clear_result(sample_game)

        row = db_connection.execute(
            "SELECT * FROM games WHERE id = ?", (sample_game,)
        ).fetchone()

        assert row["completed"] == 0
        assert row["home_score"] is None


class TestGameRepositoryIsCompleted:
    """Test is_completed() method."""

    def test_is_completed_true(self, game_repo, completed_game):
        """Test checking a completed game."""
        assert game_repo.is_completed(completed_game) is True

    def test_is_completed_false(self, game_repo, sample_game):
        """Test checking an incomplete game."""
        assert game_repo.is_completed(sample_game) is False

    def test_is_completed_nonexistent_game(self, game_repo):
        """Test checking a game that doesn't exist."""
        assert game_repo.is_completed("nonexistent") is False

    def test_is_completed_after_save(self, game_repo, sample_game):
        """Test that is_completed reflects save_result."""
        assert game_repo.is_completed(sample_game) is False

        result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=3,
            away_score=2,
            innings_played=9,
            winner="Home",
            winning_margin=1,
        )

        game_repo.save_result(sample_game, result, "team-home")

        assert game_repo.is_completed(sample_game) is True

    def test_is_completed_after_clear(self, game_repo, completed_game):
        """Test that is_completed reflects clear_result."""
        assert game_repo.is_completed(completed_game) is True

        game_repo.clear_result(completed_game)

        assert game_repo.is_completed(completed_game) is False
