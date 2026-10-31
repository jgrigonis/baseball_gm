# tests/api/test_career.py
"""Each person's career record (services/career.py) and their GM profile
page (/gms/{username}). The record is copied out of the league as it runs,
so it survives the person leaving and the league being deleted."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import career, sim_jobs
from src.api.services.leave_league import leave_league
from src.db.repositories.career_repo import CareerRepository
from src.league import divisions


def _id():
    return str(uuid.uuid4())


def _person(db, factory, league, name, team):
    """A human GM with an account and a username."""
    gm = factory.gm(team=team, league=league, is_ai=False)
    user_id = _id()
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username, created_at)"
        " VALUES (%s, %s, %s, %s, '2026-03-04 10:00:00+00')",
        (user_id, user_id, name, f"{name.lower()}-{user_id[:8]}"),
    )
    db.execute(
        "UPDATE gms SET user_id = %s, display_name = %s WHERE id = %s",
        (user_id, name, gm.id),
    )
    return gm, user_id


def _game(db, season, winner, loser, series_id=None, completed=1):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed)
           VALUES (%s, '2025-06-01', %s, %s, %s, %s, 5, 3, %s, %s)""",
        (gid, season.id, series_id, winner.id, loser.id,
         winner.id if completed else None, completed),
    )  # fmt: skip
    if completed:
        for team, won in ((winner, 1), (loser, 0)):
            db.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
                " VALUES (%s, %s, %s, %s, %s)",
                (gid, team.id, 5 if won else 3, won, 1 - won),
            )
    return gid


def _series(db, season, name, winner, loser, wins=4, losses=0):
    sid = _id()
    db.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
        (sid, season.id, name),
    )
    for _ in range(wins):
        _game(db, season, winner, loser, sid)
    for _ in range(losses):
        _game(db, season, loser, winner, sid)


def _rows(db, user_id):
    return CareerRepository(db).for_user(user_id)


@pytest.fixture
def league(db_conn, factory):
    """A league in 2025 with Mine (a person's team) and two AI teams."""
    league = factory.league(state="season")
    db_conn.execute(
        "UPDATE leagues SET name = 'Weekend League' WHERE id = %s", (league.id,)
    )
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="Amsterdam", mascot="Captains")
    a = factory.team(city="Tokyo", mascot="Samurai")
    b = factory.team(city="Dublin", mascot="Shamrocks")
    for t in (mine, a, b):
        factory.league_season_team(league, season, t)
    factory.gm(team=a, league=league)
    factory.gm(team=b, league=league)
    gm, user_id = _person(db_conn, factory, league, "Josh", mine)
    return {
        "league": league, "season": season, "mine": mine, "a": a, "b": b,
        "gm": gm, "user_id": user_id,
    }  # fmt: skip


class TestRecord:
    def test_keeps_the_regular_season_record(self, db_conn, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        _game(db_conn, league["season"], league["mine"], league["b"])
        _game(db_conn, league["season"], league["a"], league["mine"])

        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert (row["wins"], row["losses"]) == (2, 1)
        assert row["league_name"] == "Weekend League"
        assert (row["team_city"], row["team_mascot"]) == ("Amsterdam", "Captains")
        assert row["season_year"] == 2025
        assert not row["final"]
        assert row["playoff_result"] is None

    def test_updates_as_the_season_goes_on(self, db_conn, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        career.record_league(db_conn, league["league"].id)
        _game(db_conn, league["season"], league["b"], league["mine"])
        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert (row["wins"], row["losses"]) == (1, 1)

    def test_no_row_before_the_first_game(self, db_conn, league):
        career.record_league(db_conn, league["league"].id)
        assert _rows(db_conn, league["user_id"]) == []

    def test_a_title_makes_the_season_final(self, db_conn, league):
        s = league["season"]
        _game(db_conn, s, league["mine"], league["a"])
        _series(db_conn, s, "1v8", league["mine"], league["b"], wins=3)
        _series(db_conn, s, "[1,8]v[4,5]", league["mine"], league["b"])
        _series(db_conn, s, "Finals", league["mine"], league["a"], losses=2)

        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert row["playoff_result"] == "Champion"
        assert row["final"]
        # Playoff games aren't in the W-L.
        assert (row["wins"], row["losses"]) == (1, 0)

    def test_how_far_they_got(self, db_conn, league):
        s = league["season"]
        _game(db_conn, s, league["mine"], league["a"])
        _series(db_conn, s, "1v8", league["mine"], league["b"], wins=3)
        _series(db_conn, s, "[1,8]v[4,5]", league["a"], league["mine"])

        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert row["playoff_result"] == "Semifinals"
        assert not row["final"]  # the Finals aren't over

    def test_a_later_season_makes_the_last_one_final(self, db_conn, factory, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        later = factory.season(year=2026)
        factory.league_season(league["league"], later)

        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert row["final"]

    def test_division_title_once_the_regular_season_is_over(self, db_conn, league):
        s = league["season"]
        divisions.save(
            db_conn,
            league["league"].id,
            [
                divisions.Conference("East", [divisions.Division("North", [league["mine"].id, league["a"].id])]),
                divisions.Conference("West", [divisions.Division("South", [league["b"].id])]),
            ],
        )  # fmt: skip
        _game(db_conn, s, league["mine"], league["a"])
        _game(db_conn, s, league["a"], league["mine"], completed=0)

        career.record_league(db_conn, league["league"].id)
        assert not _rows(db_conn, league["user_id"])[0]["division_title"]

        db_conn.execute(
            "DELETE FROM games WHERE season_id = %s AND completed = 0", (s.id,)
        )
        career.record_league(db_conn, league["league"].id)
        assert _rows(db_conn, league["user_id"])[0]["division_title"]

    def test_backstory_seasons_dont_count(self, db_conn, factory, league):
        past = factory.season(year=2020)
        db_conn.execute(
            "UPDATE seasons SET is_backstory = TRUE WHERE id = %s", (past.id,)
        )
        factory.league_season(league["league"], past)
        _game(db_conn, past, league["mine"], league["a"])

        career.record_league(db_conn, league["league"].id)

        assert _rows(db_conn, league["user_id"]) == []

    def test_tutorial_leagues_dont_count(self, db_conn, league):
        db_conn.execute(
            "UPDATE leagues SET is_practice = TRUE WHERE id = %s",
            (league["league"].id,),
        )
        _game(db_conn, league["season"], league["mine"], league["a"])

        career.record_league(db_conn, league["league"].id)

        assert _rows(db_conn, league["user_id"]) == []

    def test_only_people_have_a_record(self, db_conn, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        _game(db_conn, league["season"], league["a"], league["b"])
        career.record_league(db_conn, league["league"].id)
        n = db_conn.execute(
            "SELECT COUNT(*) AS n FROM gm_career_seasons WHERE league_id = %s",
            (league["league"].id,),
        ).fetchone()["n"]
        assert n == 1

    def test_backfill_fills_existing_leagues(self, db_conn, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        career.backfill(db_conn)
        assert len(_rows(db_conn, league["user_id"])) == 1


class TestLeaving:
    def test_record_stops_where_they_left(self, db_conn, factory, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        _person(db_conn, factory, league["league"], "Sam", factory.team())

        leave_league(db_conn, league["league"].id, league["gm"].id)
        # The AI keeps playing their old team.
        _game(db_conn, league["season"], league["mine"], league["b"])
        career.record_league(db_conn, league["league"].id)

        (row,) = _rows(db_conn, league["user_id"])
        assert (row["wins"], row["losses"]) == (1, 0)
        assert row["final"]

    def test_record_outlives_the_league(self, db_conn, league):
        _game(db_conn, league["season"], league["mine"], league["a"])

        # The last person out deletes the league.
        leave_league(db_conn, league["league"].id, league["gm"].id)

        assert not db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league["league"].id,)
        ).fetchone()
        (row,) = _rows(db_conn, league["user_id"])
        assert (row["wins"], row["league_name"]) == (1, "Weekend League")


class TestSimJobs:
    def test_a_problem_never_undoes_the_sim(self, db_conn, league, monkeypatch):
        def boom(conn, league_id):
            conn.execute("SELECT 1/0")

        monkeypatch.setattr(career, "record_league", boom)
        _game(db_conn, league["season"], league["mine"], league["a"])
        sim_jobs._record_careers(db_conn, league["league"].id)
        # The connection still works, and the game is still there.
        assert (
            db_conn.execute(
                "SELECT COUNT(*) AS n FROM games WHERE season_id = %s",
                (league["season"].id,),
            ).fetchone()["n"]
            == 1
        )

    def test_jobs_update_the_record(self, db_conn, league, monkeypatch):
        _game(db_conn, league["season"], league["mine"], league["a"])
        monkeypatch.setitem(sim_jobs.KINDS, "sim", lambda conn, lid, params: {})
        job = {"id": _id(), "league_id": league["league"].id, "kind": "sim",
               "params": {}, "attempts": 0}  # fmt: skip

        class Jobs:
            conn = None

            def finish(self, *a):
                pass

        sim_jobs.run(db_conn, job, Jobs())

        assert len(_rows(db_conn, league["user_id"])) == 1


class TestProfilePage:
    @pytest.fixture
    def client(self, db_conn, league):
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {
            "id": league["user_id"], "username": None, "has_password": False,
        }  # fmt: skip
        yield TestClient(app, follow_redirects=False)
        app.dependency_overrides.clear()

    def _username(self, db, user_id):
        return db.execute(
            "SELECT username FROM users WHERE id = %s", (user_id,)
        ).fetchone()["username"]

    def test_shows_the_career(self, client, db_conn, league):
        s = league["season"]
        _game(db_conn, s, league["mine"], league["a"])
        _game(db_conn, s, league["mine"], league["b"])
        _game(db_conn, s, league["b"], league["mine"])
        _series(db_conn, s, "Finals", league["mine"], league["a"])
        career.record_league(db_conn, league["league"].id)

        r = client.get(f"/gms/{self._username(db_conn, league['user_id'])}")

        assert r.status_code == 200
        html = r.text
        assert "Josh" in html
        assert "GM since March 2026" in html
        assert "Trophy case" in html
        assert "Champions" in html
        assert "Weekend League" in html
        assert "2-1" in html
        assert ".667" in html
        assert "Active" in html

    def test_someone_with_no_seasons(self, client, db_conn, league):
        r = client.get(f"/gms/{self._username(db_conn, league['user_id'])}")
        assert r.status_code == 200
        assert "Trophy case" not in r.text
        assert "Your record starts with your first game" in r.text

    def test_no_such_gm(self, client):
        assert client.get("/gms/nobody-at-all").status_code == 404

    def test_any_case_goes_to_one_address(self, client, db_conn, league):
        name = self._username(db_conn, league["user_id"])
        r = client.get(f"/gms/{name.upper()}")
        assert r.status_code == 301
        assert r.headers["location"] == f"/gms/{name}"

    def test_a_league_they_left_shows_as_left(self, client, db_conn, factory, league):
        _game(db_conn, league["season"], league["mine"], league["a"])
        leave_league(db_conn, league["league"].id, league["gm"].id)
        r = client.get(f"/gms/{self._username(db_conn, league['user_id'])}")
        assert "Left" in r.text
        assert f'href="/leagues/{league["league"].id}/"' not in r.text

    def test_league_page_links_people_to_their_profiles(self, client, db_conn, league):
        db_conn.execute(
            "UPDATE leagues SET state = 'season' WHERE id = %s", (league["league"].id,)
        )
        app.dependency_overrides[get_gm_or_viewer] = lambda: {
            "id": league["gm"].id, "team_id": league["mine"].id,
        }  # fmt: skip
        r = client.get(f"/leagues/{league['league'].id}/league")
        name = self._username(db_conn, league["user_id"])
        assert f'href="/gms/{name}"' in r.text
