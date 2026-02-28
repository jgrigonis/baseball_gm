# tests/db/repositories/test_season_repo.py
import pytest
import sqlite3

from src.db.repositories.season_repo import SeasonRepository


@pytest.fixture
def db_connection():
    """Create in-memory SQLite database with seasons table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create seasons table
    conn.execute(
        """
        CREATE TABLE seasons (
            id TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(year, name)
        )
    """
    )

    yield conn
    conn.close()


@pytest.fixture
def season_repo(db_connection):
    """Create SeasonRepository instance."""
    return SeasonRepository(db_connection)


class TestSeasonRepositoryCreateSeason:
    """Test create_season() method."""

    def test_create_new_season(self, season_repo, db_connection):
        """Test creating a new season."""
        season_id = season_repo.create_season(2025)

        assert season_id is not None
        assert isinstance(season_id, str)
        assert len(season_id) == 32  # UUID hex string

        # Verify in database
        row = db_connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        assert row is not None
        assert row["year"] == 2025
        assert row["name"] == "Season2025"

    def test_create_season_with_custom_name(self, season_repo, db_connection):
        """Test creating a season with custom name."""
        season_id = season_repo.create_season(2025, "Spring Season")

        row = db_connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        assert row["year"] == 2025
        assert row["name"] == "Spring Season"

    def test_create_season_idempotent(self, season_repo):
        """Test that creating same season returns existing ID."""
        # Create first time
        season_id_1 = season_repo.create_season(2025, "Test Season")

        # Create again with same year/name
        season_id_2 = season_repo.create_season(2025, "Test Season")

        # Should return the same ID
        assert season_id_1 == season_id_2

    def test_create_multiple_seasons_same_year(self, season_repo, db_connection):
        """Test creating multiple seasons for the same year with different names."""
        spring_id = season_repo.create_season(2025, "Spring")
        fall_id = season_repo.create_season(2025, "Fall")

        assert spring_id != fall_id

        # Verify both exist
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM seasons WHERE year = ?", (2025,)
        ).fetchone()["count"]

        assert count == 2

    def test_create_seasons_different_years(self, season_repo):
        """Test creating seasons for different years."""
        season_2024 = season_repo.create_season(2024)
        season_2025 = season_repo.create_season(2025)
        season_2026 = season_repo.create_season(2026)

        # All should be different
        assert season_2024 != season_2025
        assert season_2025 != season_2026
        assert season_2024 != season_2026

    def test_create_season_default_name_format(self, season_repo, db_connection):
        """Test that default name follows 'Season{year}' format."""
        season_id = season_repo.create_season(2025)

        row = db_connection.execute(
            "SELECT name FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        assert row["name"] == "Season2025"

    def test_create_season_commits_to_db(self, season_repo, db_connection):
        """Test that season is committed to database."""
        season_id = season_repo.create_season(2025)

        # Close and reopen connection to verify commit
        db_connection.commit()

        row = db_connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        assert row is not None


class TestSeasonRepositoryGetSeason:
    """Test get_season() method."""

    def test_get_existing_season(self, season_repo):
        """Test getting an existing season."""
        season_id = season_repo.create_season(2025, "Test Season")

        season = season_repo.get_season(season_id)

        assert season is not None
        assert season["id"] == season_id
        assert season["year"] == 2025
        assert season["name"] == "Test Season"

    def test_get_nonexistent_season(self, season_repo):
        """Test getting a season that doesn't exist."""
        season = season_repo.get_season("nonexistent-id")

        assert season is None

    def test_get_season_returns_all_fields(self, season_repo):
        """Test that get_season returns all expected fields."""
        season_id = season_repo.create_season(2025, "Test")

        season = season_repo.get_season(season_id)

        expected_fields = {"id", "year", "name"}
        assert set(season.keys()) == expected_fields


class TestSeasonRepositoryGetSeasonsByYear:
    """Test get_seasons_by_year() method."""

    def test_get_seasons_by_year_single(self, season_repo):
        """Test getting seasons for a year with one season."""
        season_id = season_repo.create_season(2025)

        seasons = season_repo.get_seasons_by_year(2025)

        assert len(seasons) == 1
        assert seasons[0]["id"] == season_id
        assert seasons[0]["year"] == 2025

    def test_get_seasons_by_year_multiple(self, season_repo):
        """Test getting seasons for a year with multiple seasons."""
        spring = season_repo.create_season(2025, "Spring")
        summer = season_repo.create_season(2025, "Summer")
        fall = season_repo.create_season(2025, "Fall")

        seasons = season_repo.get_seasons_by_year(2025)

        assert len(seasons) == 3
        season_ids = [s["id"] for s in seasons]
        assert spring in season_ids
        assert summer in season_ids
        assert fall in season_ids

    def test_get_seasons_by_year_ordered_by_name(self, season_repo):
        """Test that seasons are ordered by name."""
        season_repo.create_season(2025, "Winter")
        season_repo.create_season(2025, "Fall")
        season_repo.create_season(2025, "Spring")
        season_repo.create_season(2025, "Summer")

        seasons = season_repo.get_seasons_by_year(2025)

        names = [s["name"] for s in seasons]
        assert names == sorted(names)

    def test_get_seasons_by_year_empty(self, season_repo):
        """Test getting seasons for a year with no seasons."""
        seasons = season_repo.get_seasons_by_year(2025)

        assert seasons == []

    def test_get_seasons_by_year_filters_correctly(self, season_repo):
        """Test that get_seasons_by_year only returns seasons for specified year."""
        season_repo.create_season(2024, "Season 2024")
        season_repo.create_season(2025, "Season 2025")
        season_repo.create_season(2026, "Season 2026")

        seasons = season_repo.get_seasons_by_year(2025)

        assert len(seasons) == 1
        assert seasons[0]["year"] == 2025


class TestSeasonRepositoryGetAllSeasons:
    """Test get_all_seasons() method."""

    def test_get_all_seasons_empty(self, season_repo):
        """Test getting all seasons when none exist."""
        seasons = season_repo.get_all_seasons()

        assert seasons == []

    def test_get_all_seasons_single(self, season_repo):
        """Test getting all seasons with one season."""
        season_id = season_repo.create_season(2025)

        seasons = season_repo.get_all_seasons()

        assert len(seasons) == 1
        assert seasons[0]["id"] == season_id

    def test_get_all_seasons_multiple(self, season_repo):
        """Test getting all seasons with multiple seasons."""
        s1 = season_repo.create_season(2023)
        s2 = season_repo.create_season(2024)
        s3 = season_repo.create_season(2025)

        seasons = season_repo.get_all_seasons()

        assert len(seasons) == 3
        season_ids = [s["id"] for s in seasons]
        assert s1 in season_ids
        assert s2 in season_ids
        assert s3 in season_ids

    def test_get_all_seasons_ordered_by_year_desc(self, season_repo):
        """Test that seasons are ordered by year descending."""
        season_repo.create_season(2023)
        season_repo.create_season(2025)
        season_repo.create_season(2024)

        seasons = season_repo.get_all_seasons()

        years = [s["year"] for s in seasons]
        assert years == [2025, 2024, 2023]

    def test_get_all_seasons_ordered_by_name_within_year(self, season_repo):
        """Test that seasons are ordered by name within same year."""
        season_repo.create_season(2025, "Winter")
        season_repo.create_season(2025, "Fall")
        season_repo.create_season(2025, "Spring")

        seasons = season_repo.get_all_seasons()

        # All from 2025, should be alphabetical
        names = [s["name"] for s in seasons]
        assert names == ["Fall", "Spring", "Winter"]

    def test_get_all_seasons_mixed_years_and_names(self, season_repo):
        """Test complex ordering with multiple years and names."""
        season_repo.create_season(2024, "Spring")
        season_repo.create_season(2025, "Winter")
        season_repo.create_season(2025, "Fall")
        season_repo.create_season(2023, "Season2023")

        seasons = season_repo.get_all_seasons()

        # Should be: 2025 Fall, 2025 Winter, 2024 Spring, 2023 Season2023
        assert seasons[0]["year"] == 2025
        assert seasons[0]["name"] == "Fall"
        assert seasons[1]["year"] == 2025
        assert seasons[1]["name"] == "Winter"
        assert seasons[2]["year"] == 2024
        assert seasons[3]["year"] == 2023


class TestSeasonRepositoryExists:
    """Test exists() method."""

    def test_exists_true(self, season_repo):
        """Test exists returns True for existing season."""
        season_id = season_repo.create_season(2025)

        assert season_repo.exists(season_id) is True

    def test_exists_false(self, season_repo):
        """Test exists returns False for nonexistent season."""
        assert season_repo.exists("nonexistent-id") is False

    def test_exists_multiple_seasons(self, season_repo):
        """Test exists with multiple seasons."""
        s1 = season_repo.create_season(2024)
        s2 = season_repo.create_season(2025)

        assert season_repo.exists(s1) is True
        assert season_repo.exists(s2) is True
        assert season_repo.exists("other-id") is False


class TestSeasonRepositoryDeleteSeason:
    """Test delete_season() method."""

    def test_delete_existing_season(self, season_repo, db_connection):
        """Test deleting an existing season."""
        season_id = season_repo.create_season(2025)

        # Verify exists
        assert season_repo.exists(season_id)

        # Delete
        season_repo.delete_season(season_id)

        # Verify deleted
        assert not season_repo.exists(season_id)

    def test_delete_nonexistent_season(self, season_repo):
        """Test deleting a season that doesn't exist (should not error)."""
        # Should not raise an error
        season_repo.delete_season("nonexistent-id")

    def test_delete_season_removes_from_database(self, season_repo, db_connection):
        """Test that delete actually removes from database."""
        season_id = season_repo.create_season(2025)

        season_repo.delete_season(season_id)

        # Query database directly
        row = db_connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()

        assert row is None

    def test_delete_one_of_multiple_seasons(self, season_repo, db_connection):
        """Test deleting one season doesn't affect others."""
        s1 = season_repo.create_season(2024)
        s2 = season_repo.create_season(2025)
        s3 = season_repo.create_season(2026)

        # Delete middle one
        season_repo.delete_season(s2)

        # Others should still exist
        assert season_repo.exists(s1)
        assert not season_repo.exists(s2)
        assert season_repo.exists(s3)

        # Count should be 2
        count = db_connection.execute(
            "SELECT COUNT(*) as count FROM seasons"
        ).fetchone()["count"]

        assert count == 2


class TestSeasonRepositoryIntegration:
    """Integration tests for typical workflows."""

    def test_full_season_lifecycle(self, season_repo):
        """Test complete season lifecycle: create, query, delete."""
        # Create season
        season_id = season_repo.create_season(2025, "Test Season")

        # Verify creation
        assert season_repo.exists(season_id)

        # Get season
        season = season_repo.get_season(season_id)
        assert season["year"] == 2025
        assert season["name"] == "Test Season"

        # Query by year
        seasons = season_repo.get_seasons_by_year(2025)
        assert len(seasons) == 1

        # Delete season
        season_repo.delete_season(season_id)
        assert not season_repo.exists(season_id)

    def test_multi_year_multi_season_workflow(self, season_repo):
        """Test managing multiple seasons across multiple years."""
        # Create multiple seasons
        _ = [
            season_repo.create_season(2024, "Spring"),
            season_repo.create_season(2024, "Fall"),
        ]

        _ = [
            season_repo.create_season(2025, "Spring"),
            season_repo.create_season(2025, "Summer"),
            season_repo.create_season(2025, "Fall"),
        ]

        # Query by year
        result_2024 = season_repo.get_seasons_by_year(2024)
        assert len(result_2024) == 2

        result_2025 = season_repo.get_seasons_by_year(2025)
        assert len(result_2025) == 3

        # Get all
        all_seasons = season_repo.get_all_seasons()
        assert len(all_seasons) == 5

        # Verify ordering (2025 first, then 2024)
        assert all_seasons[0]["year"] == 2025
        assert all_seasons[-1]["year"] == 2024

    def test_idempotent_creation_workflow(self, season_repo):
        """Test that repeated creation is idempotent."""
        # Create season multiple times
        id1 = season_repo.create_season(2025, "Season")
        id2 = season_repo.create_season(2025, "Season")
        id3 = season_repo.create_season(2025, "Season")

        # All should be the same
        assert id1 == id2 == id3

        # Only one season should exist
        seasons = season_repo.get_seasons_by_year(2025)
        assert len(seasons) == 1
