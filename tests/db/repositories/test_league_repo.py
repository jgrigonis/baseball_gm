# tests/db/repositories/test_league_repo.py
import pytest
import uuid

from src.db.repositories.league_repo import LeagueRepository


@pytest.fixture
def league_repo(db_conn):
    return LeagueRepository(db_conn)


@pytest.fixture
def sample_season(factory):
    return factory.season()


@pytest.fixture
def sample_team(factory):
    return factory.team(city="Boston", mascot="Red Sox")


class TestLeagueRepositoryCreateLeague:

    def test_create_new_league(self, league_repo, db_conn):
        league_id = league_repo.create_league("MLB")

        assert league_id is not None
        assert isinstance(league_id, str)
        assert len(league_id) == 32

        row = db_conn.execute(
            "SELECT * FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        assert row is not None
        assert row["name"] == "MLB"

    def test_create_league_returns_existing_id(self, league_repo, db_conn):
        league_id_1 = league_repo.create_league("MLB")
        league_id_2 = league_repo.create_league("MLB")
        assert league_id_1 == league_id_2

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM leagues WHERE name = %s", ("MLB",)
        ).fetchone()["n"]
        assert count == 1

    def test_create_multiple_leagues(self, league_repo, db_conn):
        import uuid

        suffix = str(uuid.uuid4())[:8]
        mlb_id = league_repo.create_league(f"MLB-{suffix}")
        nba_id = league_repo.create_league(f"NBA-{suffix}")
        nfl_id = league_repo.create_league(f"NFL-{suffix}")

        assert mlb_id != nba_id
        assert mlb_id != nfl_id
        assert nba_id != nfl_id

    def test_create_league_idempotent(self, league_repo):
        import uuid

        name = f"Test League {uuid.uuid4()}"
        league_id = league_repo.create_league(name)
        for _ in range(5):
            assert league_repo.create_league(name) == league_id


class TestLeagueRepositoryAssignSeasonToLeague:

    def test_assign_season_to_league(self, league_repo, db_conn, sample_season):
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season.id)

        row = db_conn.execute(
            "SELECT * FROM league_seasons WHERE league_id = %s AND season_id = %s",
            (league_id, sample_season.id),
        ).fetchone()
        assert row is not None
        assert row["league_id"] == league_id
        assert row["season_id"] == sample_season.id

    def test_assign_multiple_seasons_to_league(self, league_repo, db_conn, factory):
        # league_id = league_repo.create_league("MLB")
        league_id = league_repo.create_league(f"MLB-{uuid.uuid4()}")
        seasons = [factory.season(year=2025 + i) for i in range(3)]

        for s in seasons:
            league_repo.assign_season_to_league(league_id, s.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = %s",
            (league_id,),
        ).fetchone()["n"]
        assert count == 3

    def test_assign_season_to_league_idempotent(
        self, league_repo, db_conn, sample_season
    ):
        league_id = league_repo.create_league("MLB")

        for _ in range(5):
            league_repo.assign_season_to_league(league_id, sample_season.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = %s AND season_id = %s",
            (league_id, sample_season.id),
        ).fetchone()["n"]
        assert count == 1


class TestLeagueRepositoryAssignToLeague:

    def test_assign_team_to_league(
        self, league_repo, db_conn, sample_season, sample_team
    ):
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season.id)
        league_repo.assign_team_to_league(league_id, sample_season.id, sample_team.id)

        row = db_conn.execute(
            """
            SELECT * FROM league_season_teams
            WHERE league_id = %s AND season_id = %s AND team_id = %s
            """,
            (league_id, sample_season.id, sample_team.id),
        ).fetchone()
        assert row is not None
        assert row["league_id"] == league_id
        assert row["season_id"] == sample_season.id
        assert row["team_id"] == sample_team.id

    def test_assign_multiple_teams_to_league(
        self, league_repo, db_conn, sample_season, factory
    ):
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season.id)
        teams = [factory.team() for _ in range(5)]

        for t in teams:
            league_repo.assign_team_to_league(league_id, sample_season.id, t.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM league_season_teams WHERE league_id = %s AND season_id = %s",
            (league_id, sample_season.id),
        ).fetchone()["n"]
        assert count == 5

    def test_assign_team_to_league_idempotent(
        self, league_repo, db_conn, sample_season, sample_team
    ):
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season.id)

        for _ in range(5):
            league_repo.assign_team_to_league(
                league_id, sample_season.id, sample_team.id
            )

        count = db_conn.execute(
            """
            SELECT COUNT(*) AS n FROM league_season_teams
            WHERE league_id = %s AND season_id = %s AND team_id = %s
            """,
            (league_id, sample_season.id, sample_team.id),
        ).fetchone()["n"]
        assert count == 1

    def test_assign_same_team_to_different_seasons(
        self, league_repo, db_conn, sample_team, factory
    ):
        league_id = league_repo.create_league("MLB")
        season_1 = factory.season(year=3200)
        season_2 = factory.season(year=3201)

        league_repo.assign_season_to_league(league_id, season_1.id)
        league_repo.assign_season_to_league(league_id, season_2.id)
        league_repo.assign_team_to_league(league_id, season_1.id, sample_team.id)
        league_repo.assign_team_to_league(league_id, season_2.id, sample_team.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM league_season_teams WHERE league_id = %s AND team_id = %s",
            (league_id, sample_team.id),
        ).fetchone()["n"]
        assert count == 2


class TestLeagueRepositoryHasSeason:

    def test_has_season_true(self, league_repo, sample_season):
        league_id = league_repo.create_league("MLB")
        league_repo.assign_season_to_league(league_id, sample_season.id)
        assert league_repo.has_season(league_id, sample_season.id) is True

    def test_has_season_false(self, league_repo, sample_season):
        league_id = league_repo.create_league("MLB")
        assert league_repo.has_season(league_id, sample_season.id) is False

    def test_has_season_nonexistent_league(self, league_repo, sample_season):
        assert league_repo.has_season("nonexistent-league", sample_season.id) is False

    def test_has_season_nonexistent_season(self, league_repo):
        league_id = league_repo.create_league("MLB")
        assert league_repo.has_season(league_id, "nonexistent-season") is False

    def test_has_season_multiple_leagues(self, league_repo, sample_season):
        import uuid

        suffix = str(uuid.uuid4())[:8]
        mlb_id = league_repo.create_league(f"MLB-{suffix}")
        nba_id = league_repo.create_league(f"NBA-{suffix}")

        league_repo.assign_season_to_league(mlb_id, sample_season.id)

        assert league_repo.has_season(mlb_id, sample_season.id) is True
        assert league_repo.has_season(nba_id, sample_season.id) is False


class TestLeagueRepositoryIntegration:

    def test_full_league_setup_workflow(self, league_repo, db_conn, factory):
        league_id = league_repo.create_league("MLB")
        season = factory.season()
        teams = [factory.team() for _ in range(3)]

        league_repo.assign_season_to_league(league_id, season.id)
        for t in teams:
            league_repo.assign_team_to_league(league_id, season.id, t.id)

        assert league_repo.has_season(league_id, season.id)

        count = db_conn.execute(
            "SELECT COUNT(*) AS n FROM league_season_teams WHERE league_id = %s AND season_id = %s",
            (league_id, season.id),
        ).fetchone()["n"]
        assert count == 3
