# tests/api/test_rivals.py
"""Head-to-head records between people (career.head_to_head, gm_head_to_head)
and the profile's Rivals section (profile_sections._rivals)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import career
from src.api.view_models.profile_sections import sections


def _id():
    return str(uuid.uuid4())


def _user(db, name):
    uid = _id()
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username) VALUES (%s, %s, %s, %s)",
        (uid, uid, name, f"{name.lower()}-{uid[:8]}"),
    )
    return uid


@pytest.fixture
def world(db_conn, factory):
    """Josh (Amsterdam) and Sam (Tokyo) in one league; Dublin is AI."""
    league = factory.league(state="season")
    db_conn.execute(
        "UPDATE leagues SET name = 'Weekend League' WHERE id = %s", (league.id,)
    )
    season = factory.season(year=2030)
    factory.league_season(league, season)
    ams = factory.team(city="Amsterdam", mascot="Captains")
    tok = factory.team(city="Tokyo", mascot="Samurai")
    dub = factory.team(city="Dublin", mascot="Druids")
    josh, sam = _user(db_conn, "Josh"), _user(db_conn, "Sam")
    gms = {}
    for key, team, user in (("ams", ams, josh), ("tok", tok, sam), ("dub", dub, None)):
        gm = factory.gm(team=team, league=league, is_ai=user is None)
        if user:
            db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (user, gm.id))
        gms[key] = gm
    return {"league": league, "season": season, "ams": ams, "tok": tok,
            "dub": dub, "josh": josh, "sam": sam, "gms": gms}  # fmt: skip


def _game(db, w, home, away, winner, series_id=None, completed=1):
    g = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               winner_id, completed, series_id)
           VALUES (%s, '2030-05-01', %s, %s, %s, %s, %s, %s)""",
        (g, w["season"].id, home.id, away.id, winner.id if winner else None,
         completed, series_id),
    )  # fmt: skip
    if completed:
        for team in (home, away):
            won = int(team.id == winner.id)
            db.execute(
                "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss) VALUES (%s, %s, 1, %s, %s)",
                (g, team.id, won, 1 - won),
            )


def _series(db, w, name):
    sid = _id()
    db.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
        (sid, w["season"].id, name),
    )
    return sid


def _h2h(db, user):
    return db.execute(
        "SELECT * FROM gm_head_to_head WHERE user_id = %s", (user,)
    ).fetchall()


class TestRecording:
    def test_both_sides_written_ai_games_left_out(self, db_conn, world):
        w = world
        _game(db_conn, w, w["ams"], w["tok"], w["ams"])
        _game(db_conn, w, w["tok"], w["ams"], w["ams"])
        _game(db_conn, w, w["tok"], w["ams"], w["tok"])
        _game(db_conn, w, w["ams"], w["dub"], w["dub"])
        _game(db_conn, w, w["ams"], w["tok"], None, completed=0)

        career.record_league(db_conn, w["league"].id)

        (mine,) = _h2h(db_conn, w["josh"])
        (theirs,) = _h2h(db_conn, w["sam"])
        assert (mine["wins"], mine["losses"]) == (2, 1)
        assert (theirs["wins"], theirs["losses"]) == (1, 2)
        assert mine["opponent_id"] == w["sam"]
        assert (mine["opponent_city"], mine["team_city"]) == ("Tokyo", "Amsterdam")
        assert not mine["final"]

    def test_playoff_series_counts_and_is_noted(self, db_conn, world):
        w = world
        sid = _series(db_conn, w, "Finals")
        for _ in range(4):
            _game(db_conn, w, w["ams"], w["tok"], w["ams"], series_id=sid)
        _game(db_conn, w, w["tok"], w["ams"], w["tok"], series_id=sid)

        career.record_league(db_conn, w["league"].id)

        (mine,) = _h2h(db_conn, w["josh"])
        (theirs,) = _h2h(db_conn, w["sam"])
        assert (mine["wins"], mine["series_round"], mine["series_won"]) == (
            4,
            "Finals",
            True,
        )
        assert (theirs["series_round"], theirs["series_won"]) == ("Finals", False)

    def test_series_in_progress_has_no_result(self, db_conn, world):
        w = world
        sid = _series(db_conn, w, "1v8")
        _game(db_conn, w, w["ams"], w["tok"], w["ams"], series_id=sid)
        career.record_league(db_conn, w["league"].id)
        (mine,) = _h2h(db_conn, w["josh"])
        assert mine["series_round"] is None

    def test_leaving_closes_both_sides(self, db_conn, world):
        w = world
        _game(db_conn, w, w["ams"], w["tok"], w["ams"])
        career.record_league(db_conn, w["league"].id, leaving_gm_id=w["gms"]["ams"].id)
        db_conn.execute("UPDATE gms SET user_id = NULL, is_ai = TRUE WHERE id = %s",
                        (w["gms"]["ams"].id,))  # fmt: skip
        # Sam keeps playing the (now AI) Amsterdam team; it no longer counts.
        _game(db_conn, w, w["ams"], w["tok"], w["tok"])
        _game(db_conn, w, w["ams"], w["tok"], w["tok"])
        career.record_league(db_conn, w["league"].id)

        (theirs,) = _h2h(db_conn, w["sam"])
        assert (theirs["wins"], theirs["losses"], theirs["final"]) == (0, 1, True)
        (mine,) = _h2h(db_conn, w["josh"])
        assert mine["final"]

    def test_record_outlives_the_league(self, db_conn, world):
        w = world
        _game(db_conn, w, w["ams"], w["tok"], w["ams"])
        career.record_league(db_conn, w["league"].id)
        db_conn.execute("DELETE FROM leagues WHERE id = %s", (w["league"].id,))
        assert len(_h2h(db_conn, w["josh"])) == 1


class TestRivalsSection:
    def _rivals(self, db, user):
        seasons = db.execute(
            "SELECT * FROM gm_career_seasons WHERE user_id = %s", (user,)
        ).fetchall()
        return sections(db, user, [dict(s) for s in seasons])["rivals"]

    def test_no_rivals(self, db_conn, world):
        assert self._rivals(db_conn, world["josh"]) == []

    def test_totals_across_seasons_with_latest_meeting(self, db_conn, world, factory):
        w = world
        _game(db_conn, w, w["ams"], w["tok"], w["ams"])
        sid = _series(db_conn, w, "[1,8]v[4,5]")
        for _ in range(4):
            _game(db_conn, w, w["tok"], w["ams"], w["tok"], series_id=sid)
        career.record_league(db_conn, w["league"].id)
        # An older season, from a league that's gone.
        db_conn.execute(
            """INSERT INTO gm_head_to_head (user_id, opponent_id, league_id, season_id,
                   league_name, season_year, team_city, team_mascot, opponent_city,
                   opponent_mascot, wins, losses, series_round, series_won, final)
               VALUES (%s, %s, 'gone', 'gone-s', 'Old League', 2025, 'Seoul', 'Tigers',
                       'Lima', 'Llamas', 10, 2, 'Finals', TRUE, TRUE)""",
            (w["josh"], w["sam"]),
        )

        (r,) = self._rivals(db_conn, w["josh"])
        assert r["name"] == "Sam"
        assert (r["wins"], r["losses"], r["pct"]) == (11, 6, ".647")
        assert r["city"] == "Tokyo"  # the latest team
        assert r["note"] == "Lost to them in the 2030 Semifinals"
        assert r["username"].startswith("sam-")

    def test_on_the_page(self, db_conn, world):
        w = world
        _game(db_conn, w, w["ams"], w["tok"], w["ams"])
        career.record_league(db_conn, w["league"].id)
        name = db_conn.execute(
            "SELECT username FROM users WHERE id = %s", (w["josh"],)
        ).fetchone()["username"]
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": w["josh"]}
        try:
            html = TestClient(app).get(f"/gms/{name}").text
        finally:
            app.dependency_overrides.clear()
        assert "Rivals · human GMs" in html
        assert 'href="/gms/sam-' in html
        assert "1-0" in html
