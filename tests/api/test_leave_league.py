# tests/api/test_leave_league.py
"""A GM can leave a league. Once it has started, AI takes over their team,
which keeps its draft picks and its place in the standings."""

import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import personas, ready_check
from src.api.services.injury_news import InjuryNews
from src.api.services.leave_league import leave_league
from src.api.view_models.standings import standings_context
from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.gm_repo import GMRepository


def _human(db, factory, league, name, team=None):
    """A human GM with a user account, like one who joined by code. GMs join
    in the order they are made."""
    gm = factory.gm(team=team, league=league, is_ai=False)
    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
        (user_id, user_id, name),
    )
    db.execute(
        "UPDATE gms SET user_id = %s, display_name = %s,"
        " created_at = clock_timestamp()::text WHERE id = %s",
        (user_id, name, gm.id),
    )
    return gm, user_id


def _gm(db, gm):
    return db.execute("SELECT * FROM gms WHERE id = %s", (gm.id,)).fetchone()


def _commissioner(db, league):
    return db.execute(
        "SELECT commissioner_gm_id FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()["commissioner_gm_id"]


def _set_commissioner(db, league, gm):
    GMRepository(db).set_commissioner(gm.id, league.id)


class TestStartedLeague:
    def test_team_goes_to_an_ai_gm(self, db_conn, factory):
        league = factory.league(state="season")
        team = factory.team()
        gm, user_id = _human(db_conn, factory, league, "Alice", team=team)
        _human(db_conn, factory, league, "Bob")

        leave_league(db_conn, league.id, gm.id)

        row = _gm(db_conn, gm)
        assert row["is_ai"]
        assert row["user_id"] is None
        assert row["team_id"] == team.id
        # A persona from the library takes over, under its own name.
        persona = db_conn.execute(
            "SELECT name FROM gm_personas WHERE id = %s", (row["persona_id"],)
        ).fetchone()
        assert row["display_name"] == persona["name"]
        assert GMRepository(db_conn).get_users_leagues(user_id) == []

    def test_draft_picks_stay_with_the_team(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season()
        draft = factory.draft(league=league, season=season)
        team, other = factory.team(), factory.team()
        gm, _ = _human(db_conn, factory, league, "Alice", team=team)
        _human(db_conn, factory, league, "Bob")
        player = factory.player_row()
        db_conn.execute(
            "INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)"
            " VALUES (%s, 1, 1, %s, %s, %s)",
            (draft.id, gm.id, team.id, player.id),
        )
        for t in (team, other):
            db_conn.execute(
                "INSERT INTO draft_pick_rights"
                " (league_id, draft_year, round, original_team_id, current_owner_id)"
                " VALUES (%s, 2026, 1, %s, %s)",
                (league.id, t.id, t.id),
            )

        leave_league(db_conn, league.id, gm.id)

        pick = db_conn.execute(
            "SELECT gm_id, team_id FROM draft_picks WHERE draft_id = %s", (draft.id,)
        ).fetchone()
        assert pick == {"gm_id": gm.id, "team_id": team.id}
        rights = db_conn.execute(
            "SELECT original_team_id, current_owner_id FROM draft_pick_rights"
            " WHERE league_id = %s AND original_team_id = %s",
            (league.id, team.id),
        ).fetchone()
        assert rights["current_owner_id"] == team.id
        # The AI drafts for the team from now on, not the GM's strategy.
        assert team.id not in GMRepository(db_conn).get_human_team_ids(league.id)

    def test_standings_show_the_team_as_ai(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season()
        factory.league_season(league, season)
        team = factory.team(city="Springfield", mascot="Isotopes")
        factory.league_season_team(league, season, team)
        gm, _ = _human(db_conn, factory, league, "Alice", team=team)
        _human(db_conn, factory, league, "Bob")

        leave_league(db_conn, league.id, gm.id)

        teams = standings_context(db_conn, league.id, season.id, None)["teams"]
        (row,) = [t for t in teams if t["team_id"] == team.id]
        assert (row["city"], row["mascot"]) == ("Springfield", "Isotopes")
        assert not row["is_human"]

    def test_waits_for_a_running_sim(self, db_conn, factory, request):
        league = factory.league(state="season")
        gm, _ = _human(db_conn, factory, league, "Alice")
        url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
        with psycopg.connect(url, row_factory=dict_row) as other:
            with league_lock(other, league.id):
                with pytest.raises(LeagueBusy):
                    leave_league(db_conn, league.id, gm.id)
        assert not _gm(db_conn, gm)["is_ai"]


class TestMultiplayer:
    def test_ready_check_stops_counting_them(self, db_conn, factory):
        league = factory.league(state="season")
        a, _ = _human(db_conn, factory, league, "Alice")
        b, _ = _human(db_conn, factory, league, "Bob")
        c, _ = _human(db_conn, factory, league, "Carol")
        ready_check.set_ready(db_conn, league.id, a.id, True)
        ready_check.set_ready(db_conn, league.id, b.id, True)

        leave_league(db_conn, league.id, c.id)

        status = ready_check.status(db_conn, league.id, a.id)
        assert [g["name"] for g in status["gms"]] == ["Alice", "Bob"]
        assert status["waiting_on"] == []

    def test_last_two_becomes_single_player(self, db_conn, factory):
        league = factory.league(state="season")
        a, _ = _human(db_conn, factory, league, "Alice")
        b, _ = _human(db_conn, factory, league, "Bob")

        leave_league(db_conn, league.id, b.id)

        assert not ready_check.is_multiplayer(db_conn, league.id)

    def test_no_more_injury_news(self, db_conn, factory):
        league = factory.league(state="season")
        a, _ = _human(db_conn, factory, league, "Alice")
        b, _ = _human(db_conn, factory, league, "Bob")
        db_conn.execute(
            "INSERT INTO gm_notifications (gm_id, kind, payload)"
            " VALUES (%s, 'injury', '{}')",
            (b.id,),
        )

        leave_league(db_conn, league.id, b.id)

        assert set(InjuryNews(db_conn, league.id).gm_teams) == {a.id}
        assert not db_conn.execute(
            "SELECT 1 FROM gm_notifications WHERE gm_id = %s", (b.id,)
        ).fetchone()


class TestCommissioner:
    def test_hands_off_to_the_longest_tenured_gm(self, db_conn, factory):
        league = factory.league(state="season")
        boss, _ = _human(db_conn, factory, league, "Al")
        older, _ = _human(db_conn, factory, league, "Bob")
        _human(db_conn, factory, league, "Cam")
        factory.gm(league=league, is_ai=True)
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, boss.id)

        assert _commissioner(db_conn, league) == older.id

    def test_other_gm_leaving_keeps_the_commissioner(self, db_conn, factory):
        league = factory.league(state="season")
        boss, _ = _human(db_conn, factory, league, "Al")
        other, _ = _human(db_conn, factory, league, "Bob")
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, other.id)

        assert _commissioner(db_conn, league) == boss.id


class TestLobby:
    def test_gm_just_leaves(self, db_conn, factory):
        league = factory.league(state="lobby")
        boss, _ = _human(db_conn, factory, league, "Al")
        other, _ = _human(db_conn, factory, league, "Bob")
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, other.id)

        assert _gm(db_conn, other) is None
        assert _commissioner(db_conn, league) == boss.id

    def test_commissioner_hands_off(self, db_conn, factory):
        league = factory.league(state="lobby")
        boss, _ = _human(db_conn, factory, league, "Al")
        other, _ = _human(db_conn, factory, league, "Bob")
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, boss.id)

        assert _gm(db_conn, boss) is None
        assert _commissioner(db_conn, league) == other.id

    def test_an_ai_gm_takes_their_place(self, db_conn, factory):
        league = factory.league(state="lobby")
        db_conn.execute("UPDATE leagues SET num_teams = 4 WHERE id = %s", (league.id,))
        boss, _ = _human(db_conn, factory, league, "Al")
        other, _ = _human(db_conn, factory, league, "Bob")
        _set_commissioner(db_conn, league, boss)
        personas.fill_lobby(db_conn, league.id)

        leave_league(db_conn, league.id, other.id)

        assert len(personas.lobby_ai_gms(db_conn, league.id)) == 3

    def test_last_gm_out_deletes_the_league(self, db_conn, factory):
        league = factory.league(state="lobby")
        boss, _ = _human(db_conn, factory, league, "Al")
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, boss.id)

        assert not db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()


class TestPage:
    @pytest.fixture
    def client(self, db_conn):
        app.dependency_overrides[get_db] = lambda: db_conn
        yield TestClient(app, follow_redirects=False)
        app.dependency_overrides.clear()

    def test_leagues_page_has_leave_button(self, client, db_conn, factory):
        league = factory.league(state="season")
        gm, user_id = _human(db_conn, factory, league, "Alice")
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id,
            "display_name": "Alice",
            "has_password": True,
        }

        r = client.get("/leagues/")

        assert f'data-league-id="{league.id}"' in r.text
        assert "leaveLeague(this)" in r.text
        # Alice is the only person in it, so leaving would delete it.
        assert 'data-last="yes"' in r.text

    def test_league_page_has_leave_button(self, client, db_conn, factory):
        league = factory.league(state="season")
        gm, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob")
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        html = client.get(f"/leagues/{league.id}/league").text

        assert "Leave League</button>" in html
        assert "An AI manager will take over your team" in html
        assert f"fetch('/leagues/{league.id}/leave'" in html

    def test_league_page_warns_the_last_gm(self, client, db_conn, factory):
        league = factory.league(state="season")
        gm, user_id = _human(db_conn, factory, league, "Alice")
        factory.gm(league=league)  # an AI GM doesn't count
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        html = client.get(f"/leagues/{league.id}/league").text

        assert "the league will be deleted for good" in html

    def test_viewers_get_no_leave_button(self, client, db_conn, factory):
        league = factory.league(state="season")
        db_conn.execute(
            "UPDATE leagues SET is_public = TRUE WHERE id = %s", (league.id,)
        )
        _human(db_conn, factory, league, "Alice")
        _, outsider = _human(db_conn, factory, factory.league(), "Carol")
        app.dependency_overrides[get_current_user] = lambda: {
            "id": outsider,
            "display_name": "Carol",
        }

        r = client.get(f"/leagues/{league.id}/league")

        assert r.status_code == 200
        assert "Leave League</button>" not in r.text

    def test_leave_route(self, client, db_conn, factory):
        league = factory.league(state="season")
        gm, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob")
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        r = client.post(f"/leagues/{league.id}/leave")

        assert r.status_code == 200
        assert _gm(db_conn, gm)["is_ai"]
        # They're out: the league turns them away now.
        assert client.post(f"/leagues/{league.id}/leave").status_code == 403


# ── The last person out deletes the league ────────────────────────────────────


def _row(db, table, **values):
    """Insert a row, filling the other required columns with placeholders."""
    cols = db.execute(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_schema = current_schema() AND table_name = %s
             AND is_nullable = 'NO' AND column_default IS NULL""",
        (table,),
    ).fetchall()
    filler = {"integer": 1, "bigint": 1, "real": 0.5, "boolean": False}
    for c in cols:
        values.setdefault(
            c["column_name"], filler.get(c["data_type"], str(uuid.uuid4()))
        )
    db.execute(
        f"INSERT INTO {table} ({', '.join(values)})"
        f" VALUES ({', '.join(['%s'] * len(values))})",
        list(values.values()),
    )


def _league_with_history(db, factory):
    """A league that has played: rows in every table a league fills, from
    drafts and games through to the offseason. Returns its league and its
    one human GM."""
    league = factory.league(state="season")
    season = factory.season()
    factory.league_season(league, season)
    home, away = factory.team(), factory.team()
    for t in (home, away):
        factory.league_season_team(league, season, t)
    gm, _ = _human(db, factory, league, "Alice", team=home)
    ai = factory.gm(team=away, league=league, is_ai=True)
    # One player created by the league, one only known from its roster.
    tagged = factory.prospect(league.id)
    untagged = factory.player_row()
    for team, p in ((home, tagged), (away, untagged)):
        _row(db, "team_players", team_id=team.id, player_id=p.id)
    p, s, lg = tagged.id, season.id, league.id

    _row(db, "player_talent_caps", player_id=p)
    _row(db, "player_skills_history", player_id=p, season_id=s)
    _row(db, "player_season_stats", player_id=p, season_id=s, team_id=home.id)
    _row(db, "player_injury_log", player_id=p, season_id=s)
    for table in ("pitcher_state", "player_energy", "player_injuries"):
        _row(db, table, player_id=p, league_id=lg)
    _row(db, "team_rotations", team_id=home.id, season_id=s, player_id=p)
    _row(db, "bullpen_roles", team_id=home.id, season_id=s, player_id=p, role="Closer")
    _row(db, "team_rotation_pointer", team_id=home.id, season_id=s)
    _row(db, "offseason_steps", season_id=s)
    series_id = str(uuid.uuid4())
    _row(db, "series", id=series_id, season_id=s)
    game_id = str(uuid.uuid4())
    _row(
        db,
        "games",
        id=game_id,
        season_id=s,
        series_id=series_id,
        home_team_id=home.id,
        away_team_id=away.id,
    )
    _row(db, "team_game_stats", game_id=game_id, team_id=home.id)
    _row(
        db,
        "player_game_stats",
        game_id=game_id,
        player_id=p,
        team_id=home.id,
        opponent_team_id=away.id,
    )
    _row(db, "player_game_fielding", game_id=game_id, player_id=p, position="c")
    _row(db, "game_lineup_slots", game_id=game_id, team_id=home.id, player_id=p)
    _row(db, "game_events", game_id=game_id, team_id=home.id, event_type="injury")
    draft = factory.draft(league=league, season=season)
    _row(db, "draft_order", draft_id=draft.id, team_id=home.id)
    _row(
        db,
        "draft_pick_rights",
        league_id=lg,
        original_team_id=home.id,
        current_owner_id=away.id,
    )
    _row(
        db, "draft_picks", draft_id=draft.id, gm_id=ai.id, team_id=away.id, player_id=p
    )
    _row(db, "gm_lineup_preferences", gm_id=gm.id, player_id=p)
    _row(db, "gm_notifications", gm_id=gm.id, kind="injury", payload="{}")
    _row(db, "gm_season_evaluations", gm_id=gm.id, season_id=s)
    _row(db, "player_retirements", player_id=p, league_id=lg, season_id=s)
    return league, gm


def _row_counts(db):
    tables = db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
    ).fetchall()
    return {
        t["tablename"]: db.execute(
            f"SELECT COUNT(*) AS n FROM {t['tablename']}"
        ).fetchone()["n"]
        for t in tables
    }


class TestLastOneOut:
    def test_deletes_everything_the_league_owns(self, db_conn, factory):
        other, _ = _league_with_history(db_conn, factory)
        before = _row_counts(db_conn)
        league, gm = _league_with_history(db_conn, factory)

        leave_league(db_conn, league.id, gm.id)

        after = _row_counts(db_conn)
        # Alice keeps her account; nothing of the league is left, and the
        # other league is untouched.
        before["users"] += 1
        assert {t: n for t, n in after.items() if n != before[t]} == {}

    def test_started_single_player_league(self, db_conn, factory):
        league = factory.league(state="season")
        gm, _ = _human(db_conn, factory, league, "Alice")
        factory.gm(league=league, is_ai=True)

        leave_league(db_conn, league.id, gm.id)

        assert not db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()

    def test_a_fired_gm_still_keeps_it(self, db_conn, factory):
        league = factory.league(state="season")
        gm, _ = _human(db_conn, factory, league, "Alice")
        fired, _ = _human(db_conn, factory, league, "Bob")
        db_conn.execute("UPDATE gms SET fired_at = NOW() WHERE id = %s", (fired.id,))

        leave_league(db_conn, league.id, gm.id)

        assert db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()


# ── A GM their owner fired ────────────────────────────────────────────────────


def _fire(db, gm):
    """What firing.py leaves behind for a person: a teamless row, fired."""
    db.execute(
        "UPDATE gms SET team_id = NULL, fired_at = NOW() WHERE id = %s", (gm.id,)
    )


class TestFired:
    @pytest.fixture
    def client(self, db_conn):
        app.dependency_overrides[get_db] = lambda: db_conn
        yield TestClient(app, follow_redirects=False)
        app.dependency_overrides.clear()

    def test_leave_route(self, client, db_conn, factory):
        league = factory.league(state="offseason")
        fired, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        r = client.post(f"/leagues/{league.id}/leave")

        assert r.status_code == 200
        assert _gm(db_conn, fired) is None
        assert GMRepository(db_conn).get_users_leagues(user_id) == []
        assert db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()

    def test_doesnt_wait_on_a_running_sim(self, db_conn, factory):
        league = factory.league(state="season")
        fired, _ = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        other = psycopg.connect(os.environ["DATABASE_TEST_URL"], row_factory=dict_row)
        try:
            with league_lock(other, league.id):
                leave_league(db_conn, league.id, fired.id)
        finally:
            other.close()

        assert _gm(db_conn, fired) is None

    def test_job_offers_go(self, db_conn, factory):
        league = factory.league(state="offseason")
        fired, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        db_conn.execute(
            "INSERT INTO gm_job_offers (league_id, user_id, year, team_id, message)"
            " VALUES (%s, %s, 2030, %s, 'Come run my team')",
            (league.id, user_id, factory.team().id),
        )

        leave_league(db_conn, league.id, fired.id)

        assert not db_conn.execute(
            "SELECT 1 FROM gm_job_offers WHERE user_id = %s", (user_id,)
        ).fetchone()

    def test_commissioner_passes_on(self, db_conn, factory):
        league = factory.league(state="offseason")
        fired, _ = _human(db_conn, factory, league, "Alice")
        bob, _ = _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        _set_commissioner(db_conn, league, fired)

        leave_league(db_conn, league.id, fired.id)

        assert _commissioner(db_conn, league) == bob.id

    def test_last_one_out_deletes_the_league(self, db_conn, factory):
        league = factory.league(state="offseason")
        fired, _ = _human(db_conn, factory, league, "Alice")
        factory.gm(league=league, team=factory.team(), is_ai=True)
        _fire(db_conn, fired)

        leave_league(db_conn, league.id, fired.id)

        assert not db_conn.execute(
            "SELECT 1 FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()

    def test_league_page_has_leave_button(self, client, db_conn, factory):
        league = factory.league(state="offseason")
        fired, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        html = client.get(f"/leagues/{league.id}/league").text

        assert "Leave League</button>" in html
        assert "takes the league off your list" in html

    def test_leagues_page_says_so(self, client, db_conn, factory):
        league = factory.league(state="offseason")
        fired, user_id = _human(db_conn, factory, league, "Alice")
        _human(db_conn, factory, league, "Bob", team=factory.team())
        _fire(db_conn, fired)
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id,
            "display_name": "Alice",
            "has_password": True,
        }

        html = client.get("/leagues/").text

        assert 'data-fired="yes"' in html
