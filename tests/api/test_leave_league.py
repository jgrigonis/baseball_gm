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
from src.api.services import ready_check
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

        leave_league(db_conn, league.id, gm.id)

        row = _gm(db_conn, gm)
        assert row["is_ai"]
        assert row["user_id"] is None
        assert row["team_id"] == team.id
        assert row["display_name"] == "AI Manager"
        assert GMRepository(db_conn).get_users_leagues(user_id) == []

    def test_draft_picks_stay_with_the_team(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season()
        draft = factory.draft(league=league, season=season)
        team, other = factory.team(), factory.team()
        gm, _ = _human(db_conn, factory, league, "Alice", team=team)
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
        # The AI drafts for the team from now on, not the GM's preference list.
        assert team.id not in GMRepository(db_conn).get_human_team_ids(league.id)

    def test_standings_show_the_team_as_ai(self, db_conn, factory):
        league = factory.league(state="season")
        season = factory.season()
        factory.league_season(league, season)
        team = factory.team(city="Springfield", mascot="Isotopes")
        factory.league_season_team(league, season, team)
        gm, _ = _human(db_conn, factory, league, "Alice", team=team)

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

    def test_no_humans_left_means_no_commissioner(self, db_conn, factory):
        league = factory.league(state="season")
        boss, _ = _human(db_conn, factory, league, "Al")
        factory.gm(league=league, is_ai=True)
        _set_commissioner(db_conn, league, boss)

        leave_league(db_conn, league.id, boss.id)

        assert _commissioner(db_conn, league) is None

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

    def test_leave_route(self, client, db_conn, factory):
        league = factory.league(state="season")
        gm, user_id = _human(db_conn, factory, league, "Alice")
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id}

        r = client.post(f"/leagues/{league.id}/leave")

        assert r.status_code == 200
        assert _gm(db_conn, gm)["is_ai"]
        # They're out: the league turns them away now.
        assert client.post(f"/leagues/{league.id}/leave").status_code == 403
