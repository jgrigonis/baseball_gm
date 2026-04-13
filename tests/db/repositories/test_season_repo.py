# tests/db/repositories/test_season_repo.py
import pytest

from src.db.repositories.season_repo import SeasonRepository

# Far-future years used as unique per-test namespaces — never used elsewhere.
# Each test class gets its own year range so cross-test contamination is impossible.
_BASE = 9000


@pytest.fixture
def season_repo(db_conn):
    return SeasonRepository(db_conn)


class TestSeasonRepositoryCreateSeason:

    def test_create_new_season(self, season_repo, db_conn):
        season_id = season_repo.create_season(_BASE + 1)
        assert season_id is not None
        assert isinstance(season_id, str)
        assert len(season_id) == 32

        row = db_conn.execute(
            "SELECT * FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        assert row is not None
        assert row["year"] == _BASE + 1
        assert row["name"] == f"Season{_BASE + 1}"

    def test_create_season_with_custom_name(self, season_repo, db_conn):
        season_id = season_repo.create_season(_BASE + 2, "Spring Season")
        row = db_conn.execute(
            "SELECT * FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        assert row["year"] == _BASE + 2
        assert row["name"] == "Spring Season"

    def test_create_multiple_seasons_same_year(self, season_repo, db_conn):
        spring_id = season_repo.create_season(_BASE + 3, "Spring")
        fall_id = season_repo.create_season(_BASE + 3, "Fall")
        assert spring_id != fall_id

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM seasons WHERE year = %s", (_BASE + 3,)
        ).fetchone()["n"]
        assert count == 2

    def test_create_seasons_different_years(self, season_repo):
        s1 = season_repo.create_season(_BASE + 10)
        s2 = season_repo.create_season(_BASE + 11)
        s3 = season_repo.create_season(_BASE + 12)
        assert len({s1, s2, s3}) == 3

    def test_create_season_default_name_format(self, season_repo, db_conn):
        season_id = season_repo.create_season(_BASE + 4)
        row = db_conn.execute(
            "SELECT name FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        assert row["name"] == f"Season{_BASE + 4}"

    def test_create_season_commits_to_db(self, season_repo, db_conn):
        season_id = season_repo.create_season(_BASE + 5)
        db_conn.commit()
        row = db_conn.execute(
            "SELECT * FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        assert row is not None


class TestSeasonRepositoryGetSeason:

    def test_get_existing_season(self, season_repo):
        season_id = season_repo.create_season(_BASE + 20, "Test Season")
        season = season_repo.get_season(season_id)
        assert season is not None
        assert season["id"] == season_id
        assert season["year"] == _BASE + 20
        assert season["name"] == "Test Season"

    def test_get_nonexistent_season(self, season_repo):
        assert season_repo.get_season("nonexistent-id") is None

    def test_get_season_returns_all_fields(self, season_repo):
        season_id = season_repo.create_season(_BASE + 21, "Test")
        season = season_repo.get_season(season_id)
        assert set(season.keys()) == {"id", "year", "name"}


class TestSeasonRepositoryGetSeasonsByYear:

    def test_get_seasons_by_year_single(self, season_repo):
        season_id = season_repo.create_season(_BASE + 30)
        seasons = season_repo.get_seasons_by_year(_BASE + 30)
        assert len(seasons) == 1
        assert seasons[0]["id"] == season_id

    def test_get_seasons_by_year_multiple(self, season_repo):
        spring = season_repo.create_season(_BASE + 31, "Spring")
        summer = season_repo.create_season(_BASE + 31, "Summer")
        fall = season_repo.create_season(_BASE + 31, "Fall")
        seasons = season_repo.get_seasons_by_year(_BASE + 31)
        assert len(seasons) == 3
        ids = {s["id"] for s in seasons}
        assert {spring, summer, fall} == ids

    def test_get_seasons_by_year_ordered_by_name(self, season_repo):
        season_repo.create_season(_BASE + 32, "Winter")
        season_repo.create_season(_BASE + 32, "Fall")
        season_repo.create_season(_BASE + 32, "Spring")
        season_repo.create_season(_BASE + 32, "Summer")
        seasons = season_repo.get_seasons_by_year(_BASE + 32)
        names = [s["name"] for s in seasons]
        assert names == sorted(names)

    def test_get_seasons_by_year_empty(self, season_repo):
        # Use a year that is guaranteed to never have been inserted
        seasons = season_repo.get_seasons_by_year(_BASE + 99)
        assert seasons == []

    def test_get_seasons_by_year_filters_correctly(self, season_repo):
        season_repo.create_season(_BASE + 33, "Season A")
        target = season_repo.create_season(_BASE + 34, "Season B")
        season_repo.create_season(_BASE + 35, "Season C")
        seasons = season_repo.get_seasons_by_year(_BASE + 34)
        assert len(seasons) == 1
        assert seasons[0]["id"] == target


class TestSeasonRepositoryGetAllSeasons:
    """
    get_all_seasons() is unscoped — it returns every season in the DB.
    Tests use unique far-future years and assert on subset membership
    and relative ordering rather than exact counts or indices.
    """

    def test_get_all_seasons_includes_created(self, season_repo):
        s1 = season_repo.create_season(_BASE + 40)
        seasons = season_repo.get_all_seasons()
        ids = {s["id"] for s in seasons}
        assert s1 in ids

    def test_get_all_seasons_includes_multiple(self, season_repo):
        s1 = season_repo.create_season(_BASE + 41)
        s2 = season_repo.create_season(_BASE + 42)
        s3 = season_repo.create_season(_BASE + 43)
        seasons = season_repo.get_all_seasons()
        ids = {s["id"] for s in seasons}
        assert {s1, s2, s3}.issubset(ids)

    def test_get_all_seasons_ordered_by_year_desc(self, season_repo):
        """Years inserted out of order — verify our three appear in desc order."""
        y_low = _BASE + 50
        y_mid = _BASE + 51
        y_high = _BASE + 52
        season_repo.create_season(y_low)
        season_repo.create_season(y_high)
        season_repo.create_season(y_mid)

        seasons = season_repo.get_all_seasons()
        # Filter to just our three years for isolation
        ours = [s for s in seasons if s["year"] in (y_low, y_mid, y_high)]
        years = [s["year"] for s in ours]
        assert years == [y_high, y_mid, y_low]

    def test_get_all_seasons_ordered_by_name_within_year(self, season_repo):
        yr = _BASE + 53
        season_repo.create_season(yr, "Winter")
        season_repo.create_season(yr, "Fall")
        season_repo.create_season(yr, "Spring")

        seasons = season_repo.get_all_seasons()
        ours = [s for s in seasons if s["year"] == yr]
        names = [s["name"] for s in ours]
        assert names == ["Fall", "Spring", "Winter"]

    def test_get_all_seasons_mixed_years_and_names(self, season_repo):
        yr_a = _BASE + 54
        yr_b = _BASE + 55
        yr_c = _BASE + 56
        season_repo.create_season(yr_b, "Spring")
        season_repo.create_season(yr_c, "Winter")
        season_repo.create_season(yr_c, "Fall")
        season_repo.create_season(yr_a, "Season")

        seasons = season_repo.get_all_seasons()
        ours = [s for s in seasons if s["year"] in (yr_a, yr_b, yr_c)]
        # Expected order: yr_c Fall, yr_c Winter, yr_b Spring, yr_a Season
        assert ours[0]["year"] == yr_c and ours[0]["name"] == "Fall"
        assert ours[1]["year"] == yr_c and ours[1]["name"] == "Winter"
        assert ours[2]["year"] == yr_b
        assert ours[3]["year"] == yr_a


class TestSeasonRepositoryExists:

    def test_exists_true(self, season_repo):
        season_id = season_repo.create_season(_BASE + 60)
        assert season_repo.exists(season_id) is True

    def test_exists_false(self, season_repo):
        assert season_repo.exists("nonexistent-id") is False

    def test_exists_multiple_seasons(self, season_repo):
        s1 = season_repo.create_season(_BASE + 61)
        s2 = season_repo.create_season(_BASE + 62)
        assert season_repo.exists(s1) is True
        assert season_repo.exists(s2) is True
        assert season_repo.exists("other-id") is False


class TestSeasonRepositoryDeleteSeason:

    def test_delete_existing_season(self, season_repo):
        season_id = season_repo.create_season(_BASE + 70)
        assert season_repo.exists(season_id)
        season_repo.delete_season(season_id)
        assert not season_repo.exists(season_id)

    def test_delete_nonexistent_season(self, season_repo):
        season_repo.delete_season("nonexistent-id")  # should not raise

    def test_delete_season_removes_from_database(self, season_repo, db_conn):
        season_id = season_repo.create_season(_BASE + 71)
        season_repo.delete_season(season_id)
        row = db_conn.execute(
            "SELECT * FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        assert row is None

    def test_delete_one_of_multiple_seasons(self, season_repo, db_conn):
        s1 = season_repo.create_season(_BASE + 72)
        s2 = season_repo.create_season(_BASE + 73)
        s3 = season_repo.create_season(_BASE + 74)

        season_repo.delete_season(s2)

        assert season_repo.exists(s1)
        assert not season_repo.exists(s2)
        assert season_repo.exists(s3)

        # Scope count to our three years only
        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM seasons WHERE year = ANY(%s)",
            ([_BASE + 72, _BASE + 73, _BASE + 74],),
        ).fetchone()["n"]
        assert count == 2


class TestSeasonRepositoryIntegration:

    def test_full_season_lifecycle(self, season_repo):
        season_id = season_repo.create_season(_BASE + 80, "Test Season")
        assert season_repo.exists(season_id)

        season = season_repo.get_season(season_id)
        assert season["year"] == _BASE + 80
        assert season["name"] == "Test Season"

        seasons = season_repo.get_seasons_by_year(_BASE + 80)
        assert len(seasons) == 1

        season_repo.delete_season(season_id)
        assert not season_repo.exists(season_id)

    def test_multi_year_multi_season_workflow(self, season_repo):
        yr24 = _BASE + 81
        yr25 = _BASE + 82
        season_repo.create_season(yr24, "Spring")
        season_repo.create_season(yr24, "Fall")
        season_repo.create_season(yr25, "Spring")
        season_repo.create_season(yr25, "Summer")
        season_repo.create_season(yr25, "Fall")

        result_24 = season_repo.get_seasons_by_year(yr24)
        assert len(result_24) == 2

        result_25 = season_repo.get_seasons_by_year(yr25)
        assert len(result_25) == 3

        all_seasons = season_repo.get_all_seasons()
        ours = [s for s in all_seasons if s["year"] in (yr24, yr25)]
        assert len(ours) == 5
        # yr25 should come before yr24 (desc)
        assert ours[0]["year"] == yr25
        assert ours[-1]["year"] == yr24
