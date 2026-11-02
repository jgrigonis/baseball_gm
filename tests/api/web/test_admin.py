# tests/api/web/test_admin.py
"""
The admin pages: only admins get in, they see every league and user, and they
can pause leagues, change settings, remove GMs and manage accounts. Also the
default admin login and the forced password change.

Routes run against the real test database and commit, so every test uses
fresh random names.
"""

import argparse
import uuid

import pytest
from fastapi.testclient import TestClient

from scripts import cligr
from src.api.database import get_db
from src.api.main import app
from src.api.services import admin as admin_service
from src.api.services import ready_check
from src.api.services.passwords import verify_password
from src.config import settings
from src.db.migration_files.migration_010_admin import DEFAULT_ADMIN_USERNAME
from src.db.repositories.user_repo import UserRepository

PASSWORD = "correct horse battery"


def _name(prefix="u"):
    return f"{prefix}_" + uuid.uuid4().hex[:10]


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


def _user(db, is_admin=False, must_change=False, email=None) -> dict:
    username = _name("admin" if is_admin else "gm")
    user_id = admin_service.create_user(
        db, username, PASSWORD, email, is_admin, must_change
    )
    return _row(db, user_id)


def _row(db, user_id) -> dict | None:
    row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    return dict(row) if row else None


def _sign_in(client, user):
    client.cookies.clear()
    r = client.post(
        "/auth/login", data={"username": user["username"], "password": PASSWORD}
    )
    assert r.status_code == 302


@pytest.fixture
def admin(client, db_conn):
    user = _user(db_conn, is_admin=True)
    _sign_in(client, user)
    return user


def _league(db, factory, state="season", **cols):
    league = factory.league(state=state)
    name = _name("League")
    db.execute(
        "UPDATE leagues SET name = %s, join_code = %s, pace_control = 'timer' WHERE id = %s",
        (name, uuid.uuid4().hex[:6].upper(), league.id),
    )
    for col, value in cols.items():
        db.execute(f"UPDATE leagues SET {col} = %s WHERE id = %s", (value, league.id))
    league.name = name
    return league


def _human_gm(db, league, user, team=None) -> str:
    gm_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, team_id, display_name, is_ai)"
        " VALUES (%s, %s, %s, %s, %s, FALSE)",
        (gm_id, league.id, user["id"], team.id if team else None, user["username"]),
    )
    db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))
    return gm_id


def _settings_form(**overrides):
    form = {
        "name": "Renamed",
        "mode": "blitz",
        "pace_control": "timer",
        "decision_window_sec": "120",
        "draft_window_sec": "300",
        "lineup_window_sec": "600",
        "sim_period_days": "3",
        "num_seasons": "10",
    }
    form.update(overrides)
    return form


# ── Getting in ────────────────────────────────────────────────────────────────


class TestDefaultAdmin:
    def test_migration_creates_admin_who_must_change_password(self, db_conn):
        row = db_conn.execute(
            "SELECT * FROM users WHERE username = %s", (DEFAULT_ADMIN_USERNAME,)
        ).fetchone()
        assert row["is_admin"]
        assert row["must_change_password"]
        assert verify_password(row["password_hash"], settings.admin_initial_password)


class TestForcedPasswordChange:
    def test_pages_send_them_to_change_password(self, client, db_conn):
        user = _user(db_conn, is_admin=True, must_change=True)
        r = client.post(
            "/auth/login", data={"username": user["username"], "password": PASSWORD}
        )
        assert r.headers["location"] == "/leagues/"

        for page in ("/leagues/", "/admin/users"):
            r = client.get(page, headers={"accept": "text/html"})
            assert r.status_code == 303
            assert r.headers["location"] == "/auth/change-password"

        assert client.get("/auth/change-password").status_code == 200

    def test_fetch_callers_get_403(self, client, db_conn):
        _sign_in(client, _user(db_conn, must_change=True))
        assert client.get("/leagues/").status_code == 403

    def test_changing_it_lets_them_in(self, client, db_conn):
        user = _user(db_conn, is_admin=True, must_change=True)
        _sign_in(client, user)

        r = client.post(
            "/auth/change-password",
            data={
                "current": PASSWORD,
                "password": "a new one!",
                "confirm": "a new one!",
            },
        )

        assert r.status_code == 302
        row = _row(db_conn, user["id"])
        assert not row["must_change_password"]
        assert verify_password(row["password_hash"], "a new one!")
        assert client.cookies["gm_session"] == row["session_token"]
        assert client.get("/admin/users").status_code == 200

    @pytest.mark.parametrize(
        "current, new, error",
        [
            ("wrong password", "a new one!", "current password is wrong"),
            (PASSWORD, PASSWORD, "different from the current one"),
            (PASSWORD, "short", "at least 8"),
        ],
    )
    def test_rejects(self, client, db_conn, current, new, error):
        user = _user(db_conn, must_change=True)
        _sign_in(client, user)

        r = client.post(
            "/auth/change-password",
            data={"current": current, "password": new, "confirm": new},
        )

        assert r.status_code == 400
        assert error in r.text
        assert _row(db_conn, user["id"])["must_change_password"]


class TestAdminOnly:
    def test_regular_user_gets_403(self, client, db_conn):
        _sign_in(client, _user(db_conn))
        for page in ("/admin/leagues", "/admin/users", "/admin/personas"):
            assert client.get(page).status_code == 403
        assert client.post("/admin/users", data={}).status_code in (403, 422)

    def test_signed_out_goes_to_landing(self, client):
        assert client.get("/admin/leagues").headers["location"] == "/"

    def test_admin_link_only_for_admins(self, client, db_conn):
        _sign_in(client, _user(db_conn))
        assert 'href="/admin/"' not in client.get("/leagues/").text
        _sign_in(client, _user(db_conn, is_admin=True))
        assert 'href="/admin/"' in client.get("/leagues/").text

    def test_admin_link_on_league_and_history_pages(self, client, db_conn, factory):
        user = _user(db_conn, is_admin=True)
        league = _league(db_conn, factory)
        _human_gm(db_conn, league, user, factory.team())
        _sign_in(client, user)
        for page in (f"/leagues/{league.id}/league", f"/leagues/{league.id}/history"):
            r = client.get(page)
            assert r.status_code == 200, page
            assert 'href="/admin/"' in r.text, page


# ── Leagues ───────────────────────────────────────────────────────────────────


class TestLeagues:
    def test_lists_every_league_with_settings(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory, sim_period_days=7, decision_window_sec=95)

        r = client.get("/admin/leagues")

        assert r.status_code == 200
        assert league.name in r.text
        assert "95 / 300 / 600" in r.text

    def test_lists_league_and_current_season_ids(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        factory.league_season(league, factory.season(year=2025))
        newest = factory.season(year=2026)
        factory.league_season(league, newest)

        r = client.get("/admin/leagues")

        assert f'title="league_id">{league.id}<' in r.text
        assert f'title="season_id">{newest.id}<' in r.text

    def test_league_page_shows_gms(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        gm_user = _user(db_conn)
        _human_gm(db_conn, league, gm_user)

        r = client.get(f"/admin/leagues/{league.id}")

        assert r.status_code == 200
        assert gm_user["username"] in r.text

    def test_commissioner_links_to_their_gm_profile(
        self, client, db_conn, factory, admin
    ):
        league = _league(db_conn, factory)
        gm_user = _user(db_conn)
        gm_id = _human_gm(db_conn, league, gm_user)
        db_conn.execute(
            "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s",
            (gm_id, league.id),
        )

        r = client.get("/admin/leagues")

        assert f'href="/gms/{gm_user["username"]}"' in r.text

    def test_unknown_league_404(self, client, admin):
        assert client.get("/admin/leagues/nope").status_code == 404


class TestPause:
    def test_pause_stops_the_league_moving_on(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        gm_user = _user(db_conn)
        _human_gm(db_conn, league, gm_user)

        r = client.post(f"/admin/leagues/{league.id}/pause")
        assert r.status_code == 303
        assert db_conn.execute(
            "SELECT is_paused FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()["is_paused"]

        _sign_in(client, gm_user)
        r = client.post(f"/leagues/{league.id}/sim", json={"count": 1})
        assert r.status_code == 409
        assert "paused" in r.json()["detail"]

    def test_paused_multiplayer_league_waits_out_its_window(self, db_conn, factory):
        league = _league(db_conn, factory, is_paused=True)
        for _ in range(2):
            _human_gm(db_conn, league, _user(db_conn))
        db_conn.execute(
            "UPDATE leagues SET period_deadline = NOW() - INTERVAL '1 hour' WHERE id = %s",
            (league.id,),
        )

        assert not ready_check.advance_if_due(db_conn, league.id)
        gm_id = db_conn.execute(
            "SELECT id FROM gms WHERE league_id = %s LIMIT 1", (league.id,)
        ).fetchone()["id"]
        assert ready_check.status(db_conn, league.id, gm_id)["paused"]

    def test_resume_starts_the_window_over(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory, is_paused=True)
        db_conn.execute(
            "UPDATE leagues SET period_deadline = NOW() - INTERVAL '1 hour' WHERE id = %s",
            (league.id,),
        )

        client.post(f"/admin/leagues/{league.id}/resume")

        row = db_conn.execute(
            "SELECT is_paused, period_deadline > NOW() AS open FROM leagues WHERE id = %s",
            (league.id,),
        ).fetchone()
        assert not row["is_paused"]
        assert row["open"]


class TestSettings:
    def test_saves(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory, state="lobby")

        r = client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(
                mode="speed_blitz", sim_period_days="30", is_public="true"
            ),
        )

        assert r.status_code == 303
        row = db_conn.execute(
            "SELECT * FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()
        assert row["name"] == "Renamed"
        assert row["mode"] == "speed_blitz"
        assert row["sim_period_days"] == 30
        assert row["is_public"]
        assert not row["reentry_enabled"]

    @pytest.mark.parametrize(
        "field, value, error",
        [
            ("sim_period_days", "31", "between 1 and 30"),
            ("decision_window_sec", "5", "between 30 and 600"),
            ("pace_control", "scheduled", "Unknown pace"),
            ("mode", "speed_blitz", "only change before the league starts"),
            ("name", "  ", "needs a name"),
            ("backstory_years", "3", "only change before the league starts"),
        ],
    )
    def test_rejects(self, client, db_conn, factory, admin, field, value, error):
        league = _league(db_conn, factory)

        r = client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(**{field: value}),
        )

        assert r.status_code == 400
        assert error in r.text
        assert (
            db_conn.execute(
                "SELECT name FROM leagues WHERE id = %s", (league.id,)
            ).fetchone()["name"]
            == league.name
        )

    def test_sets_the_years_of_history_before_the_start(
        self, client, db_conn, factory, admin
    ):
        league = _league(db_conn, factory, state="lobby")

        r = client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(backstory_years="8"),
        )

        assert r.status_code == 303
        assert (
            db_conn.execute(
                "SELECT backstory_years FROM leagues WHERE id = %s", (league.id,)
            ).fetchone()["backstory_years"]
            == 8
        )

    def test_years_of_history_stay_in_range(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory, state="lobby")

        r = client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(backstory_years="16"),
        )

        assert r.status_code == 400
        assert "between 0 and 15" in r.text

    def test_changes_commissioner(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        gm_id = _human_gm(db_conn, league, _user(db_conn))

        client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(commissioner_gm_id=gm_id),
        )

        assert (
            db_conn.execute(
                "SELECT commissioner_gm_id FROM leagues WHERE id = %s", (league.id,)
            ).fetchone()["commissioner_gm_id"]
            == gm_id
        )

    def test_commissioner_must_be_a_person_in_the_league(
        self, client, db_conn, factory, admin
    ):
        league = _league(db_conn, factory)
        ai = factory.gm(league=league)

        r = client.post(
            f"/admin/leagues/{league.id}/settings",
            data=_settings_form(commissioner_gm_id=ai.id),
        )

        assert r.status_code == 400
        assert "human GMs" in r.text


class TestRemoveGM:
    def test_started_league_hands_team_to_ai(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        stays = _human_gm(db_conn, league, _user(db_conn))
        leaves = _human_gm(db_conn, league, _user(db_conn), team=factory.team())

        r = client.post(f"/admin/leagues/{league.id}/gms/{leaves}/remove")

        assert r.headers["location"] == f"/admin/leagues/{league.id}?done=removed"
        gm = db_conn.execute("SELECT * FROM gms WHERE id = %s", (leaves,)).fetchone()
        assert gm["is_ai"] and gm["user_id"] is None and gm["team_id"]
        assert db_conn.execute("SELECT 1 FROM gms WHERE id = %s", (stays,)).fetchone()

    def test_last_person_deletes_league(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory, state="lobby")
        gm_id = _human_gm(db_conn, league, _user(db_conn))

        r = client.post(f"/admin/leagues/{league.id}/gms/{gm_id}/remove")

        assert r.headers["location"] == "/admin/leagues?done=league_deleted"
        assert not db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()

    def test_ai_gm_cannot_be_removed(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        ai = factory.gm(league=league)

        r = client.post(f"/admin/leagues/{league.id}/gms/{ai.id}/remove")

        assert r.status_code == 400


# ── Users ─────────────────────────────────────────────────────────────────────


class TestUsers:
    def test_lists_users_with_emails(self, client, db_conn, admin):
        email = _name() + "@example.com"
        user = _user(db_conn, email=email)

        r = client.get("/admin/users")

        assert user["username"] in r.text
        assert email in r.text

    def test_usernames_link_to_gm_profiles(self, client, db_conn, admin):
        user = _user(db_conn)

        r = client.get("/admin/users")

        assert f'href="/gms/{user["username"]}"' in r.text

    def test_add_user(self, client, db_conn, admin):
        username = _name()
        r = client.post(
            "/admin/users",
            data={
                "username": username,
                "password": PASSWORD,
                "email": f"{username}@example.com",
                "must_change": "true",
            },
        )

        assert r.status_code == 303
        row = UserRepository(db_conn).get_by_username(username)
        full = _row(db_conn, row["id"])
        assert full["email"] == f"{username}@example.com"
        assert full["must_change_password"]
        assert not full["is_admin"]
        assert verify_password(full["password_hash"], PASSWORD)

    @pytest.mark.parametrize(
        "form, error",
        [
            ({"username": "x"}, "3–30"),
            ({"password": "short"}, "at least 8"),
            ({"email": "not-an-email"}, "look like an email"),
        ],
    )
    def test_add_user_rejects(self, client, admin, form, error):
        data = {"username": _name(), "password": PASSWORD, "email": "", **form}
        r = client.post("/admin/users", data=data)
        assert r.status_code == 400
        assert error in r.text

    def test_add_user_taken_username(self, client, db_conn, admin):
        taken = _user(db_conn)["username"].upper()
        r = client.post("/admin/users", data={"username": taken, "password": PASSWORD})
        assert r.status_code == 400
        assert "taken" in r.text

    def test_set_and_clear_email(self, client, db_conn, admin):
        user = _user(db_conn)
        email = _name() + "@example.com"

        client.post(f"/admin/users/{user['id']}/email", data={"email": email})
        assert _row(db_conn, user["id"])["email"] == email

        client.post(f"/admin/users/{user['id']}/email", data={"email": " "})
        assert _row(db_conn, user["id"])["email"] is None

    def test_email_must_be_unique(self, client, db_conn, admin):
        email = _name() + "@example.com"
        _user(db_conn, email=email)
        user = _user(db_conn)

        r = client.post(
            f"/admin/users/{user['id']}/email", data={"email": email.upper()}
        )

        assert r.status_code == 400
        assert "Another user has that email" in r.text

    def test_set_password_signs_them_out(self, client, db_conn, admin):
        user = _user(db_conn)

        r = client.post(
            f"/admin/users/{user['id']}/password",
            data={
                "password": "brand new pw",
                "confirm": "brand new pw",
                "must_change": "true",
            },
        )

        assert r.status_code == 303
        row = _row(db_conn, user["id"])
        assert verify_password(row["password_hash"], "brand new pw")
        assert row["must_change_password"]
        assert row["session_token"] != user["session_token"]

    def test_set_password_mismatch(self, client, db_conn, admin):
        user = _user(db_conn)
        r = client.post(
            f"/admin/users/{user['id']}/password",
            data={"password": "brand new pw", "confirm": "something else"},
        )
        assert r.status_code == 400
        assert "match" in r.text

    def test_make_and_unmake_admin(self, client, db_conn, admin):
        user = _user(db_conn)

        client.post(f"/admin/users/{user['id']}/admin", data={"is_admin": "true"})
        assert _row(db_conn, user["id"])["is_admin"]

        client.post(f"/admin/users/{user['id']}/admin", data={})
        assert not _row(db_conn, user["id"])["is_admin"]

    def test_cannot_unmake_self(self, client, db_conn, admin):
        r = client.post(f"/admin/users/{admin['id']}/admin", data={})
        assert r.status_code == 400
        assert _row(db_conn, admin["id"])["is_admin"]

    def test_delete_user_leaves_their_leagues(self, client, db_conn, factory, admin):
        league = _league(db_conn, factory)
        user = _user(db_conn)
        _human_gm(db_conn, league, _user(db_conn))
        gm_id = _human_gm(db_conn, league, user, team=factory.team())

        r = client.post(f"/admin/users/{user['id']}/delete")

        assert r.headers["location"] == "/admin/users?done=user_deleted"
        assert _row(db_conn, user["id"]) is None
        gm = db_conn.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()
        assert gm["is_ai"] and gm["user_id"] is None

    def test_cannot_delete_self(self, client, db_conn, admin):
        r = client.post(f"/admin/users/{admin['id']}/delete")
        assert r.status_code == 400
        assert _row(db_conn, admin["id"])


# ── CLI ───────────────────────────────────────────────────────────────────────


class TestMakeAdminCommand:
    @pytest.fixture(autouse=True)
    def setup(self, db_conn, monkeypatch):
        monkeypatch.setattr(cligr, "get_connection", lambda: db_conn)
        monkeypatch.setattr(cligr.getpass, "getpass", lambda _prompt: "cli password")

    def _run(self, username, reset=False):
        cligr.cmd_make_admin(
            argparse.Namespace(username=username, reset_password=reset)
        )

    def test_promotes_existing_user(self, db_conn):
        user = _user(db_conn)
        self._run(user["username"])
        row = _row(db_conn, user["id"])
        assert row["is_admin"]
        assert row["password_hash"] == user["password_hash"]

    def test_reset_password(self, db_conn):
        user = _user(db_conn, is_admin=True)
        self._run(user["username"], reset=True)
        assert verify_password(
            _row(db_conn, user["id"])["password_hash"], "cli password"
        )

    def test_creates_missing_user(self, db_conn):
        username = _name()
        self._run(username)
        row = UserRepository(db_conn).get_by_username(username)
        assert row["is_admin"]


class TestPersonas:
    def _create(self, client, name, **extra):
        data = {
            "name": name,
            "bio": "Loves a bunt.",
            "archetype": "Small-Ball Sam",
            "chance": "70",
            "small_ball": "90",
        } | extra
        return client.post("/admin/personas", data=data)

    def _get(self, db, name):
        row = db.execute(
            "SELECT * FROM gm_personas WHERE name = %s", (name,)
        ).fetchone()
        return dict(row) if row else None

    def test_list_shows_the_library(self, client, admin):
        r = client.get("/admin/personas")
        assert r.status_code == 200
        assert "GM Personas" in r.text
        assert "The Old Scout" in r.text
        assert "Create a Persona" in r.text

    def test_create(self, client, db_conn, admin):
        name = _name("Persona")
        r = self._create(client, name)
        p = self._get(db_conn, name)
        assert r.status_code == 303
        assert (
            r.headers["location"] == f"/admin/personas/{p['id']}?done=persona_created"
        )
        assert p["chance"] == 70
        assert p["dials"]["small_ball"] == 90
        assert p["dials"]["risk"] == 50  # not on the form: neutral

        page = client.get(f"/admin/personas/{p['id']}").text
        assert name in page
        assert "small ball all day" in page
        assert ">90<" in page  # admins see the numbers

    def test_create_checks_the_form(self, client, db_conn, admin):
        name = _name("Persona")
        assert self._create(client, name).status_code == 303
        r = self._create(client, name)
        assert r.status_code == 400
        assert "already a persona with that name" in r.text
        r = self._create(client, _name("Persona"), chance="101")
        assert r.status_code == 400
        assert "Chance is a whole number" in r.text
        assert self._create(client, "x").status_code == 400

    def test_duplicate_prefills_the_form(self, client, db_conn, admin):
        name = _name("Persona")
        self._create(client, name, risk="12")
        p = self._get(db_conn, name)
        page = client.get(f"/admin/personas?from={p['id']}").text
        assert f"Duplicate {name}" in page
        assert 'name="risk" min="0" max="100" step="1" value="12"' in page
        assert 'name="name" value=""' in page

    def test_only_chance_changes(self, client, db_conn, admin):
        name = _name("Persona")
        self._create(client, name)
        p = self._get(db_conn, name)
        r = client.post(f"/admin/personas/{p['id']}/chance", data={"chance": "0"})
        assert r.status_code == 303
        after = self._get(db_conn, name)
        assert after["chance"] == 0
        assert after["dials"] == p["dials"]
        r = client.post(f"/admin/personas/{p['id']}/chance", data={"chance": "abc"})
        assert r.status_code == 400

    def test_delete_only_when_no_league_uses_it(self, client, db_conn, factory, admin):
        name = _name("Persona")
        self._create(client, name)
        p = self._get(db_conn, name)
        gm = factory.gm(team=factory.team(), league=_league(db_conn, factory))
        db_conn.execute(
            "UPDATE gms SET persona_id = %s WHERE id = %s", (p["id"], gm.id)
        )

        r = client.post(f"/admin/personas/{p['id']}/delete")
        assert r.status_code == 400
        assert "can't be deleted" in r.text
        assert self._get(db_conn, name)

        db_conn.execute("UPDATE gms SET persona_id = NULL WHERE id = %s", (gm.id,))
        r = client.post(f"/admin/personas/{p['id']}/delete")
        assert r.status_code == 303
        assert self._get(db_conn, name) is None
