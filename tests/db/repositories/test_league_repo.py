# tests/db/repositories/test_league_repo.py
import pytest
import sqlite3

from src.db.repositories.league_repo import LeagueRepository


@pytest.fixture
def db_connection():
    """Create in-memory SQLite database with league tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create leagues table
    conn.execute(
        """
        CREATE TABLE leagues (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    """
    )

    # Create league_seasons table
    conn.execute(
        """
        CREATE TABLE league_seasons (
            league_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            PRIMARY KEY (league_id, season_id),
            FOREIGN KEY (league_id) REFERENCES leagues(id),
            FOREIGN KEY (season_id) REFERENCES seasons(id)
        )
    """
    )

    # Create league_season_teams table
    conn.execute(
        """
        CREATE TABLE league_season_teams (
            league_id TEXT NOT NULL,
            season_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            PRIMARY KEY (league_id, season_id, team_id),
            FOREIGN KEY (league_id) REFERENCES leagues(id),
            FOREIGN KEY (season_id) REFERENCES seasons(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """
    )

    # Create seasons table (for foreign key)
    conn.execute(
        """
        CREATE TABLE seasons (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            year INTEGER NOT NULL
        )
    """
    )

    # Create teams table (for foreign key)
    conn.execute(
        """
        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            mascot TEXT NOT NULL
        )
    """
    )

    yield conn
    conn.close()


@pytest.fixture
def league_repo(db_connection):
    """Create LeagueRepository instance."""
    return LeagueRepository(db_connection)


@pytest.fixture
def sample_season(db_connection):
    """Insert a sample season."""
    db_connection.execute(
        "INSERT INTO seasons (id, name, year) VALUES (?, ?, ?)",
        ("season-1", "Season 1", 2025),
    )
    db_connection.commit()
    return "season-1"


@pytest.fixture
def sample_team(db_connection):
    """Insert a sample team."""
    db_connection.execute(
        "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
        ("team-1", "Boston", "Red Sox"),
    )
    db_connection.commit()
    return "team-1"


class TestLeagueRepositoryCreateLeague:
    """Test create_league() method."""

    def test_create_new_league(self, league_repo, db_connection):
        """Test creating a new league."""
        league_id = league_repo.create_league("MLB")

        assert league_id is not None
        assert isinstance(league_id, str)
        assert len(league_id) == 32  # UUID hex string

        # Verify in database
        row = db_connection.execute(
            "SELECT * FROM leagues WHERE id = ?", (league_id,)
        ).fetchone()

        assert row is not None
        assert row["name"] == "MLB"

    def test_create_league_returns_existing_id(self, league_repo, db_connection):
        """Test that creating a league with existing name returns existing ID."""
        # Create first time
        league_id_1 = league_repo.create_league("MLB")

        # Try to create again with same name
        league_id_2 = league_repo.create_league("MLB")

        # Should return the same ID
        assert league_id_1 == league_id_2

        # Should only have one row in database
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM leagues WHERE name = ?", ("MLB",)
        ).fetchone()["count"]

        assert count == 1

    def test_create_multiple_leagues(self, league_repo, db_connection):
        """Test creating multiple leagues with different names."""
        mlb_id = league_repo.create_league("MLB")
        nba_id = league_repo.create_league("NBA")
        nfl_id = league_repo.create_league("NFL")

        # All should be different
        assert mlb_id != nba_id
        assert mlb_id != nfl_id
        assert nba_id != nfl_id

        # All should exist in database
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM leagues"
        ).fetchone()["count"]

        assert count == 3

    def test_create_league_idempotent(self, league_repo):
        """Test that create_league is idempotent."""
        league_id = league_repo.create_league("Test League")

        # Call multiple times
        for _ in range(5):
            returned_id = league_repo.create_league("Test League")
            assert returned_id == league_id


class TestLeagueRepositoryAssignSeasonToLeague:
    """Test assign_season_to_league() method."""

    def test_assign_season_to_league(self, league_repo, db_connection, sample_season):
        """Test assigning a season to a league."""
        league_id = league_repo.create_league("MLB")

        league_repo.assign_season_to_league(league_id, sample_season)

        # Verify in database
        row = db_connection.execute(
            """
            SELECT * FROM league_seasons 
            WHERE league_id = ? AND season_id = ?
            """,
            (league_id, sample_season),
        ).fetchone()

        assert row is not None
        assert row["league_id"] == league_id
        assert row["season_id"] == sample_season

    def test_assign_multiple_seasons_to_league(self, league_repo, db_connection):
        """Test assigning multiple seasons to one league."""
        league_id = league_repo.create_league("MLB")

        # Create multiple seasons
        seasons = []
        for i in range(3):
            season_id = f"season-{i}"
            db_connection.execute(
                "INSERT INTO seasons (id, name, year) VALUES (?, ?, ?)",
                (season_id, f"Season {i}", 2025 + i),
            )
            seasons.append(season_id)

        db_connection.commit()

        # Assign all seasons
        for season_id in seasons:
            league_repo.assign_season_to_league(league_id, season_id)

        # Verify all are assigned
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM league_seasons WHERE league_id = ?",
            (league_id,),
        ).fetchone()["count"]

        assert count == 3

    def test_assign_season_to_league_idempotent(
        self, league_repo, db_connection, sample_season
    ):
        """Test that assign_season_to_league is idempotent (INSERT OR IGNORE)."""
        league_id = league_repo.create_league("MLB")

        # Assign multiple times
        for _ in range(5):
            league_repo.assign_season_to_league(league_id, sample_season)

        # Should only have one row
        count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM league_seasons 
            WHERE league_id = ? AND season_id = ?
            """,
            (league_id, sample_season),
        ).fetchone()["count"]

        assert count == 1


class TestLeagueRepositoryAssignToLeague:
    """Test assign_to_league() method."""

    def test_assign_team_to_league(
        self, league_repo, db_connection, sample_season, sample_team
    ):
        """Test assigning a team to a league for a season."""
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season)

        league_repo.assign_to_league(league_id, sample_season, sample_team)

        # Verify in database
        row = db_connection.execute(
            """
            SELECT * FROM league_season_teams 
            WHERE league_id = ? AND season_id = ? AND team_id = ?
            """,
            (league_id, sample_season, sample_team),
        ).fetchone()

        assert row is not None
        assert row["league_id"] == league_id
        assert row["season_id"] == sample_season
        assert row["team_id"] == sample_team

    def test_assign_multiple_teams_to_league(
        self, league_repo, db_connection, sample_season
    ):
        """Test assigning multiple teams to a league."""
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season)

        # Create multiple teams
        teams = []
        for i in range(5):
            team_id = f"team-{i}"
            db_connection.execute(
                "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
                (team_id, f"City {i}", f"Mascot {i}"),
            )
            teams.append(team_id)

        db_connection.commit()

        # Assign all teams
        for team_id in teams:
            league_repo.assign_to_league(league_id, sample_season, team_id)

        # Verify all are assigned
        count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM league_season_teams 
            WHERE league_id = ? AND season_id = ?
            """,
            (league_id, sample_season),
        ).fetchone()["count"]

        assert count == 5

    def test_assign_to_league_idempotent(
        self, league_repo, db_connection, sample_season, sample_team
    ):
        """Test that assign_to_league is idempotent (INSERT OR IGNORE)."""
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season)

        # Assign multiple times
        for _ in range(5):
            league_repo.assign_to_league(league_id, sample_season, sample_team)

        # Should only have one row
        count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM league_season_teams 
            WHERE league_id = ? AND season_id = ? AND team_id = ?
            """,
            (league_id, sample_season, sample_team),
        ).fetchone()["count"]

        assert count == 1

    def test_assign_same_team_to_different_seasons(
        self, league_repo, db_connection, sample_team
    ):
        """Test assigning the same team to multiple seasons."""
        league_id = league_repo.create_league("MLB")

        # Create two seasons
        season_1 = "season-2025"
        season_2 = "season-2026"

        for season_id, year in [(season_1, 2025), (season_2, 2026)]:
            db_connection.execute(
                "INSERT INTO seasons (id, name, year) VALUES (?, ?, ?)",
                (season_id, f"Season {year}", year),
            )
            league_repo.assign_season_to_league(league_id, season_id)

        db_connection.commit()

        # Assign team to both seasons
        league_repo.assign_to_league(league_id, season_1, sample_team)
        league_repo.assign_to_league(league_id, season_2, sample_team)

        # Should have two rows
        count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM league_season_teams 
            WHERE league_id = ? AND team_id = ?
            """,
            (league_id, sample_team),
        ).fetchone()["count"]

        assert count == 2


class TestLeagueRepositoryHasSeason:
    """Test has_season() method."""

    def test_has_season_true(self, league_repo, sample_season):
        """Test has_season returns True when season is assigned."""
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season)

        assert league_repo.has_season(league_id, sample_season) is True

    def test_has_season_false(self, league_repo, sample_season):
        """Test has_season returns False when season is not assigned."""
        league_id = league_repo.create_league("MLB")

        assert league_repo.has_season(league_id, sample_season) is False

    def test_has_season_nonexistent_league(self, league_repo, sample_season):
        """Test has_season with nonexistent league."""
        assert league_repo.has_season("nonexistent-league", sample_season) is False

    def test_has_season_nonexistent_season(self, league_repo):
        """Test has_season with nonexistent season."""
        league_id = league_repo.create_league("MLB")

        assert league_repo.has_season(league_id, "nonexistent-season") is False

    def test_has_season_multiple_leagues(self, league_repo, sample_season):
        """Test has_season with multiple leagues."""
        mlb_id = league_repo.create_league("MLB")
        nba_id = league_repo.create_league("NBA")

        # Only assign season to MLB
        league_repo.assign_season_to_league(mlb_id, sample_season)

        assert league_repo.has_season(mlb_id, sample_season) is True
        assert league_repo.has_season(nba_id, sample_season) is False


class TestLeagueRepositoryIntegration:
    """Integration tests for typical workflows."""

    def test_full_league_setup_workflow(self, league_repo, db_connection):
        """Test complete workflow of setting up a league with teams."""
        # Create league
        league_id = league_repo.create_league("MLB")

        # Create season
        season_id = "2025-season"
        db_connection.execute(
            "INSERT INTO seasons (id, name, year) VALUES (?, ?, ?)",
            (season_id, "2025 Season", 2025),
        )

        # Create teams
        team_ids = []
        for i in range(3):
            team_id = f"team-{i}"
            db_connection.execute(
                "INSERT INTO teams (id, city, mascot) VALUES (?, ?, ?)",
                (team_id, f"City {i}", f"Team {i}"),
            )
            team_ids.append(team_id)

        db_connection.commit()

        # Assign season to league
        league_repo.assign_season_to_league(league_id, season_id)

        # Assign all teams to league
        for team_id in team_ids:
            league_repo.assign_to_league(league_id, season_id, team_id)

        # Verify setup
        assert league_repo.has_season(league_id, season_id)

        team_count = db_connection.execute(
            """
            SELECT COUNT(*) as count FROM league_season_teams 
            WHERE league_id = ? AND season_id = ?
            """,
            (league_id, season_id),
        ).fetchone()["count"]

        assert team_count == 3
