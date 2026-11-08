# tests/api/test_badges.py
"""Badges on the GM profile (services/badges.py): each rule, awarding them
once and keeping them, and how the profile and admin pages show them."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_admin, get_current_user
from src.api.main import app
from src.api.services import badges, career, sim_jobs
from src.api.services.leave_league import leave_league


def _id():
    return str(uuid.uuid4())


def _user(db, email=None):
    uid = _id()
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username, email)"
        " VALUES (%s, %s, 'Josh', %s, %s)",
        (uid, uid, f"josh-{uid[:8]}", email),
    )
    return uid


def _season(db, user_id, league_id="L1", year=2030, **cols):
    """A gm_career_seasons row, as career.record_league would write it."""
    row = {
        "user_id": user_id,
        "league_id": league_id,
        "season_id": _id(),
        "league_name": f"League {league_id}",
        "season_year": year,
        "team_city": "Amsterdam",
        "team_mascot": "Captains",
        "wins": 81,
        "losses": 81,
        "final": True,
        **cols,
    }
    names = ", ".join(row)
    marks = ", ".join(f"%({k})s" for k in row)
    db.execute(f"INSERT INTO gm_career_seasons ({names}) VALUES ({marks})", row)


def _check(db, user_id, key):
    return badges.check_all(db, user_id)[key]


class TestCareerBadges:
    def test_champion(self, db_conn):
        u = _user(db_conn)
        assert not _check(db_conn, u, "champion").earned
        _season(db_conn, u, year=2031, playoff_result="Champion")
        c = _check(db_conn, u, "champion")
        assert c.earned and c.detail == "League L1 · 2031"

    def test_custom_team_leagues_earn_nothing(self, db_conn):
        """A league with custom teams (single player) counts for no badge."""
        u = _user(db_conn)
        _season(db_conn, u, year=2031, playoff_result="Champion", custom_teams=True)
        assert not _check(db_conn, u, "champion").earned
        _season(db_conn, u, "B", year=2032, playoff_result="Champion")
        assert _check(db_conn, u, "champion").detail == "League B · 2032"

    def test_dynasty_needs_three_in_one_league(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, "A", 2030, playoff_result="Champion")
        _season(db_conn, u, "A", 2032, playoff_result="Champion")
        _season(db_conn, u, "B", 2031, playoff_result="Champion")
        c = _check(db_conn, u, "dynasty")
        assert not c.earned and c.progress == (2, 3)
        _season(db_conn, u, "A", 2034, playoff_result="Champion")
        c = _check(db_conn, u, "dynasty")
        assert c.earned and c.detail == "League A · 2034"

    def test_back_to_back(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, "A", 2030, playoff_result="Champion")
        _season(db_conn, u, "A", 2032, playoff_result="Champion")
        assert not _check(db_conn, u, "back_to_back").earned
        _season(db_conn, u, "A", 2033, playoff_result="Champion")
        assert _check(db_conn, u, "back_to_back").detail == "League A · 2033"

    def test_hundred_wins(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, wins=97, losses=65)
        c = _check(db_conn, u, "hundred_wins")
        assert not c.earned and c.progress == (97, 100)
        _season(db_conn, u, year=2031, wins=101, losses=61)
        assert _check(db_conn, u, "hundred_wins").earned

    def test_worst_to_first(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, "A", 2030, finish=5, finish_of=5)
        _season(db_conn, u, "A", 2031, finish=2, finish_of=5)
        _season(db_conn, u, "A", 2032, finish=1, finish_of=5)
        assert not _check(db_conn, u, "worst_to_first").earned  # not the next season
        _season(db_conn, u, "B", 2030, finish=6, finish_of=6)
        _season(db_conn, u, "B", 2031, finish=1, finish_of=6)
        assert _check(db_conn, u, "worst_to_first").detail == "League B · 2031"

    def test_sweep_and_trades(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, trades=20)
        assert _check(db_conn, u, "wheeler_dealer").progress == (20, 25)
        _season(db_conn, u, year=2031, trades=5, sweeps=1)
        assert _check(db_conn, u, "wheeler_dealer").earned
        assert _check(db_conn, u, "sweep").earned

    def test_account_badges(self, db_conn):
        u = _user(db_conn, email="josh@example.com")
        assert _check(db_conn, u, "email").earned
        assert not _check(db_conn, u, "contributor").earned
        db_conn.execute("UPDATE users SET is_contributor = TRUE WHERE id = %s", (u,))
        assert _check(db_conn, u, "contributor").earned


class TestLeagueBadges:
    @pytest.fixture
    def setup(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season(year=2030)
        factory.league_season(league, season)
        mine, other = factory.team(city="Amsterdam"), factory.team(city="Tokyo")
        gm = factory.gm(team=mine, league=league, is_ai=False)
        factory.gm(team=other, league=league)
        u = _user(db_conn)
        db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (u, gm.id))
        return {"league": league, "season": season, "mine": mine, "other": other,
                "gm": gm, "user": u}  # fmt: skip

    def _drafted_all_star(self, db, s, rnd):
        draft = db.execute(
            "SELECT id FROM drafts WHERE league_id = %s", (s["league"].id,)
        ).fetchone()
        if not draft:
            draft_id = _id()
            db.execute(
                "INSERT INTO drafts (id, league_id, season_id, format) VALUES (%s, %s, %s, 'preference')",
                (draft_id, s["league"].id, s["season"].id),
            )
        else:
            draft_id = draft["id"]
        pid = _id()
        db.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws, league_id)"
            " VALUES (%s, 'Ines', 'Barros', 'R', 'R', %s)",
            (pid, s["league"].id),
        )
        n = db.execute("SELECT COUNT(*) AS n FROM draft_picks").fetchone()["n"] + 1
        db.execute(
            """INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (draft_id, n, rnd, s["gm"].id, s["mine"].id, pid),
        )
        db.execute(
            "INSERT INTO all_stars (season_id, player_id, team_id, slot) VALUES (%s, %s, %s, 'ss')",
            (s["season"].id, pid, s["mine"].id),
        )

    def test_scouts_eye_and_late_round_gem(self, db_conn, setup):
        self._drafted_all_star(db_conn, setup, 1)
        self._drafted_all_star(db_conn, setup, 2)
        assert _check(db_conn, setup["user"], "scouts_eye").progress == (2, 3)
        assert not _check(db_conn, setup["user"], "late_round_gem").earned
        self._drafted_all_star(db_conn, setup, 7)
        assert _check(db_conn, setup["user"], "scouts_eye").earned
        gem = _check(db_conn, setup["user"], "late_round_gem")
        assert gem.earned and gem.detail == "Ines Barros, round 7"

    def test_all_star_captain(self, db_conn, setup):
        db_conn.execute(
            """INSERT INTO all_star_games (season_id, captain1_team_id, captain2_team_id, state)
               VALUES (%s, %s, %s, 'played')""",
            (setup["season"].id, setup["other"].id, setup["mine"].id),
        )
        assert _check(db_conn, setup["user"], "all_star_captain").earned

    def test_derby_boss(self, db_conn, setup):
        pid = _id()
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws) VALUES (%s, 'Hal', 'Homer', 'R', 'R')",
            (pid,),
        )
        db_conn.execute(
            """INSERT INTO hr_derby_results (season_id, round, match, player_id, team_id, seed, won)
               VALUES (%s, 1, 1, %s, %s, 1, TRUE)""",
            (setup["season"].id, pid, setup["mine"].id),
        )
        # Won a first-round match, but there's a final still to come.
        other = _id()
        db_conn.execute(
            "INSERT INTO players (id, first_name, last_name, bats, throws) VALUES (%s, 'X', 'Y', 'R', 'R')",
            (other,),
        )
        db_conn.execute(
            """INSERT INTO hr_derby_results (season_id, round, match, player_id, team_id, seed, won)
               VALUES (%s, 2, 1, %s, %s, 2, TRUE)""",
            (setup["season"].id, other, setup["other"].id),
        )
        assert not _check(db_conn, setup["user"], "derby_boss").earned
        db_conn.execute("UPDATE hr_derby_results SET team_id = %s WHERE player_id = %s",
                        (setup["mine"].id, other))  # fmt: skip
        assert _check(db_conn, setup["user"], "derby_boss").earned

    def test_full_run(self, db_conn, setup):
        db_conn.execute(
            "UPDATE leagues SET state = 'complete' WHERE id = %s", (setup["league"].id,)
        )
        assert not _check(db_conn, setup["user"], "full_run").earned
        _season(db_conn, setup["user"], setup["league"].id)
        assert _check(db_conn, setup["user"], "full_run").earned

    def test_rookie_gm_needs_a_tutorial_season_through_the_finals(self, db_conn, setup):
        db_conn.execute(
            "UPDATE leagues SET is_practice = TRUE WHERE id = %s", (setup["league"].id,)
        )
        assert not _check(db_conn, setup["user"], "rookie_gm").earned
        finals = _id()
        db_conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
            (finals, setup["season"].id),
        )
        for _ in range(4):
            db_conn.execute(
                """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
                       away_team_id, winner_id, completed)
                   VALUES (%s, '2030-10-01', %s, %s, %s, %s, %s, 1)""",
                (_id(), setup["season"].id, finals, setup["mine"].id,
                 setup["other"].id, setup["other"].id),
            )  # fmt: skip
        assert _check(db_conn, setup["user"], "rookie_gm").earned

    def test_tutorial_leagues_count_for_nothing_else(self, db_conn, setup):
        db_conn.execute(
            "UPDATE leagues SET is_practice = TRUE WHERE id = %s", (setup["league"].id,)
        )
        db_conn.execute(
            """INSERT INTO all_star_games (season_id, captain1_team_id, captain2_team_id, state)
               VALUES (%s, %s, %s, 'played')""",
            (setup["season"].id, setup["mine"].id, setup["other"].id),
        )
        assert not _check(db_conn, setup["user"], "all_star_captain").earned


class TestAwarding:
    def test_stored_once_and_kept(self, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, year=2031, playoff_result="Champion")
        assert badges.award(db_conn, u) == ["champion"]
        assert badges.award(db_conn, u) == []
        # Even once the season that earned it is gone.
        db_conn.execute("DELETE FROM gm_career_seasons WHERE user_id = %s", (u,))
        assert badges.earned(db_conn, u)["champion"]["detail"] == "League L1 · 2031"

    def test_leaving_awards_before_the_team_goes(self, db_conn, factory):
        league = factory.league(state="complete")
        season = factory.season(year=2030)
        factory.league_season(league, season)
        team = factory.team()
        gm = factory.gm(team=team, league=league, is_ai=False)
        u = _user(db_conn)
        db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (u, gm.id))
        _season(db_conn, u, league.id)

        leave_league(db_conn, league.id, gm.id)

        assert "full_run" in badges.earned(db_conn, u)

    def test_sim_jobs_award_badges(self, db_conn, factory, monkeypatch):
        league = factory.league(state="season")
        gm = factory.gm(team=factory.team(), league=league, is_ai=False)
        u = _user(db_conn, email="a@example.com")
        db_conn.execute("UPDATE gms SET user_id = %s WHERE id = %s", (u, gm.id))
        monkeypatch.setattr(career, "record_league", lambda conn, lid: None)

        sim_jobs._record_careers(db_conn, league.id)

        assert "email" in badges.earned(db_conn, u)


class TestPages:
    @pytest.fixture
    def client(self, db_conn):
        app.dependency_overrides[get_db] = lambda: db_conn
        yield TestClient(app, follow_redirects=False)
        app.dependency_overrides.clear()

    def test_profile_shows_earned_and_locked(self, client, db_conn):
        u = _user(db_conn)
        _season(db_conn, u, year=2031, playoff_result="Champion", trades=19)
        badges.award(db_conn, u)
        app.dependency_overrides[get_current_user] = lambda: {"id": u}
        name = db_conn.execute(
            "SELECT username FROM users WHERE id = %s", (u,)
        ).fetchone()["username"]

        html = client.get(f"/gms/{name}").text

        assert f"Badges · 1 of {len(badges.BADGES)}" in html
        assert "League L1 · 2031" in html
        assert "19 of 25" in html  # Wheeler-Dealer, still locked
        assert 'class="gp-badge locked"' in html

    def test_admin_sets_and_unsets_paid_contributor(self, client, db_conn):
        u = _user(db_conn)
        app.dependency_overrides[get_admin] = lambda: {"id": _id(), "is_admin": True}

        r = client.post(
            f"/admin/users/{u}/contributor", data={"is_contributor": "true"}
        )
        assert r.status_code == 303
        assert "contributor" in badges.earned(db_conn, u)

        client.post(f"/admin/users/{u}/contributor", data={})
        assert "contributor" not in badges.earned(db_conn, u)
