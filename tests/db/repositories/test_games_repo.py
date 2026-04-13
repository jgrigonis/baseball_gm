# tests/db/repositories/test_games_repo.py
import pytest

from src.db.repositories.games_repo import GameRepository
from src.game.game import GameResult


@pytest.fixture
def game_repo(db_conn):
    return GameRepository(db_conn)


@pytest.fixture
def base(db_conn, factory):
    """Season + two teams used by most fixtures."""
    from types import SimpleNamespace

    season = factory.season()
    home_team = factory.team(city="Home City", mascot="Homers")
    away_team = factory.team(city="Away City", mascot="Visitors")
    return SimpleNamespace(
        conn=db_conn,
        season=season,
        home=home_team,
        away=away_team,
    )


@pytest.fixture
def sample_game(base):
    """An incomplete game."""
    import uuid

    gid = str(uuid.uuid4())
    base.conn.execute(
        """
        INSERT INTO games (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (gid, "2025-04-01", base.season.id, None, base.home.id, base.away.id, 0),
    )
    base.gid = gid
    return base


@pytest.fixture
def completed_game(base):
    """A completed game with scores."""
    import uuid

    gid = str(uuid.uuid4())
    base.conn.execute(
        """
        INSERT INTO games (
            id, game_date, season_id, series_id, home_team_id, away_team_id,
            home_score, away_score, completed, innings_played, winner_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            gid,
            "2025-04-02",
            base.season.id,
            None,
            base.home.id,
            base.away.id,
            5,
            3,
            1,
            9,
            base.home.id,
        ),
    )
    base.gid = gid
    return base


class TestGameRepositoryGet:

    def test_get_existing_game(self, game_repo, sample_game):
        result = game_repo.get(sample_game.gid)
        assert result is not None
        assert result["game_id"] == sample_game.gid
        assert result["season_id"] == sample_game.season.id
        assert result["home_team_id"] == sample_game.home.id
        assert result["away_team_id"] == sample_game.away.id
        assert result["game_date"] == "2025-04-01"
        assert result["completed"] == 0
        assert result["home_score"] is None
        assert result["away_score"] is None
        assert result["winner_id"] is None
        assert result["innings_played"] is None

    def test_get_completed_game(self, game_repo, completed_game):
        result = game_repo.get(completed_game.gid)
        assert result is not None
        assert result["game_id"] == completed_game.gid
        assert result["completed"] == 1
        assert result["home_score"] == 5
        assert result["away_score"] == 3
        assert result["winner_id"] == completed_game.home.id
        assert result["innings_played"] == 9

    def test_get_nonexistent_game(self, game_repo):
        assert game_repo.get("nonexistent-game") is None

    def test_get_returns_all_fields(self, game_repo, sample_game):
        result = game_repo.get(sample_game.gid)
        assert set(result.keys()) == {
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


class TestGameRepositorySaveResult:

    def test_save_result_basic(self, game_repo, sample_game):
        result = GameResult(
            home_team="Home Team",
            away_team="Away Team",
            home_score=5,
            away_score=3,
            innings_played=9,
            winner="Home Team",
            winning_margin=2,
        )
        game_repo.save_game_result(sample_game.gid, result, sample_game.home.id)

        row = sample_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (sample_game.gid,)
        ).fetchone()
        assert row["home_score"] == 5
        assert row["away_score"] == 3
        assert row["winner_id"] == sample_game.home.id
        assert row["innings_played"] == 9
        assert row["completed"] == 1

    def test_save_result_extra_innings(self, game_repo, sample_game):
        result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=4,
            away_score=3,
            innings_played=12,
            winner="Home",
            winning_margin=1,
        )
        game_repo.save_game_result(sample_game.gid, result, sample_game.home.id)

        row = sample_game.conn.execute(
            "SELECT innings_played FROM games WHERE id = %s", (sample_game.gid,)
        ).fetchone()
        assert row["innings_played"] == 12

    def test_save_result_marks_completed(self, game_repo, sample_game):
        row = sample_game.conn.execute(
            "SELECT completed FROM games WHERE id = %s", (sample_game.gid,)
        ).fetchone()
        assert row["completed"] == 0

        result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=1,
            away_score=0,
            innings_played=9,
            winner="Home",
            winning_margin=1,
        )
        game_repo.save_game_result(sample_game.gid, result, sample_game.home.id)

        row = sample_game.conn.execute(
            "SELECT completed FROM games WHERE id = %s", (sample_game.gid,)
        ).fetchone()
        assert row["completed"] == 1

    def test_save_result_overwrites_existing(self, game_repo, completed_game):
        new_result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=10,
            away_score=8,
            innings_played=11,
            winner="Home",
            winning_margin=2,
        )
        game_repo.save_game_result(
            completed_game.gid, new_result, completed_game.home.id
        )

        row = completed_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (completed_game.gid,)
        ).fetchone()
        assert row["home_score"] == 10
        assert row["away_score"] == 8
        assert row["innings_played"] == 11


class TestGameRepositoryGetSeasonGames:

    @pytest.fixture
    def season_games(self, db_conn, factory):
        """Two seasons with multiple games each."""
        from types import SimpleNamespace
        import uuid

        s1 = factory.season(year=3100)
        s2 = factory.season(year=3101)
        teams = [factory.team() for _ in range(5)]

        games_s1 = []
        for i, (home, away, completed, hs, as_) in enumerate(
            [
                (teams[0], teams[1], 0, None, None),
                (teams[1], teams[2], 1, 5, 3),
                (teams[2], teams[3], 1, 2, 1),
                (teams[3], teams[4], 0, None, None),
            ]
        ):
            gid = str(uuid.uuid4())
            db_conn.execute(
                """
                INSERT INTO games (id, game_date, season_id, series_id,
                    home_team_id, away_team_id, completed, home_score, away_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    gid,
                    f"2025-04-{i+1:02d}",
                    s1.id,
                    None,
                    home.id,
                    away.id,
                    completed,
                    hs,
                    as_,
                ),
            )
            games_s1.append(gid)

        gid_s2 = str(uuid.uuid4())
        db_conn.execute(
            """
            INSERT INTO games (id, game_date, season_id, series_id,
                home_team_id, away_team_id, completed, home_score, away_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (gid_s2, "2025-04-01", s2.id, None, teams[0].id, teams[1].id, 1, 4, 2),
        )

        return SimpleNamespace(
            conn=db_conn,
            s1=s1,
            s2=s2,
            games_s1=games_s1,
            game_s2=gid_s2,
        )

    def test_get_all_season_games(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s1.id)
        assert len(games) == 4
        assert all(g["season_id"] == season_games.s1.id for g in games)

    def test_get_season_games_ordered_by_date(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s1.id)
        dates = [g["game_date"] for g in games]
        assert dates == sorted(dates)

    def test_get_completed_games_only(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s1.id, completed_only=True)
        assert len(games) == 2
        assert all(g["completed"] == 1 for g in games)

    def test_get_incomplete_games_only(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s1.id, incomplete_only=True)
        assert len(games) == 2
        assert all(g["completed"] in (0, None) for g in games)

    def test_get_games_different_season(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s2.id)
        assert len(games) == 1
        assert games[0]["game_id"] == season_games.game_s2

    def test_get_season_games_empty(self, game_repo):
        games = game_repo.get_season_games("nonexistent-season")
        assert games == []

    def test_get_season_games_returns_all_fields(self, game_repo, season_games):
        games = game_repo.get_season_games(season_games.s1.id)
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

    def test_clear_result_completed_game(self, game_repo, completed_game):
        row = completed_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (completed_game.gid,)
        ).fetchone()
        assert row["completed"] == 1
        assert row["home_score"] == 5

        game_repo.clear_result(completed_game.gid)

        row = completed_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (completed_game.gid,)
        ).fetchone()
        assert row["completed"] == 0
        assert row["home_score"] is None
        assert row["away_score"] is None
        assert row["winner_id"] is None
        assert row["innings_played"] is None

    def test_clear_result_preserves_game_info(self, game_repo, completed_game):
        game_repo.clear_result(completed_game.gid)

        row = completed_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (completed_game.gid,)
        ).fetchone()
        assert row["id"] == completed_game.gid
        assert row["season_id"] == completed_game.season.id
        assert row["home_team_id"] == completed_game.home.id
        assert row["away_team_id"] == completed_game.away.id
        assert row["game_date"] == "2025-04-02"

    def test_clear_result_incomplete_game(self, game_repo, sample_game):
        game_repo.clear_result(sample_game.gid)

        row = sample_game.conn.execute(
            "SELECT * FROM games WHERE id = %s", (sample_game.gid,)
        ).fetchone()
        assert row["completed"] == 0
        assert row["home_score"] is None


class TestGameRepositoryIsCompleted:

    def test_is_completed_true(self, game_repo, completed_game):
        assert game_repo.is_completed(completed_game.gid) is True

    def test_is_completed_false(self, game_repo, sample_game):
        assert game_repo.is_completed(sample_game.gid) is False

    def test_is_completed_nonexistent_game(self, game_repo):
        assert game_repo.is_completed("nonexistent") is False

    def test_is_completed_after_save(self, game_repo, sample_game):
        assert game_repo.is_completed(sample_game.gid) is False

        result = GameResult(
            home_team="Home",
            away_team="Away",
            home_score=3,
            away_score=2,
            innings_played=9,
            winner="Home",
            winning_margin=1,
        )
        game_repo.save_game_result(sample_game.gid, result, sample_game.home.id)
        assert game_repo.is_completed(sample_game.gid) is True

    def test_is_completed_after_clear(self, game_repo, completed_game):
        assert game_repo.is_completed(completed_game.gid) is True
        game_repo.clear_result(completed_game.gid)
        assert game_repo.is_completed(completed_game.gid) is False
