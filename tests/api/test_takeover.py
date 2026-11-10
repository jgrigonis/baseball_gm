# tests/api/test_takeover.py
"""A person can join a running league between seasons by taking over a team
an AI GM runs (services/takeover.py), if the commissioner allows late
joiners. Their career record starts with the first season they run it."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_user
from src.api.main import app
from src.api.services import career, owner_office, takeover
from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.gm_repo import GMRepository


def _id():
    return str(uuid.uuid4())


def _user(db, name):
    user_id = _id()
    db.execute(
        "INSERT INTO users (id, session_token, display_name, username, created_at)"
        " VALUES (%s, %s, %s, %s, '2026-03-04 10:00:00+00')",
        (user_id, user_id, name, f"{name.lower()}-{user_id[:8]}"),
    )
    return {"id": user_id, "display_name": name}


def _person(db, factory, league, name, team):
    gm = factory.gm(team=team, league=league, is_ai=False)
    user = _user(db, name)
    db.execute(
        "UPDATE gms SET user_id = %s, display_name = %s WHERE id = %s",
        (user["id"], name, gm.id),
    )
    return gm, user


def _game(db, season, winner, loser):
    gid = _id()
    db.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed)
           VALUES (%s, '2025-06-01', %s, %s, %s, 5, 3, %s, 1)""",
        (gid, season.id, winner.id, loser.id, winner.id),
    )
    for team, won in ((winner, 1), (loser, 0)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, %s, %s, %s)",
            (gid, team.id, 5 if won else 3, won, 1 - won),
        )


def _set(db, league, **cols):
    for col, val in cols.items():
        db.execute(f"UPDATE leagues SET {col} = %s WHERE id = %s", (val, league.id))


def _gm(db, gm_id):
    return db.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()


@pytest.fixture
def setup(db_conn, factory):
    """A league done with its 2025 season: Alice runs Captains, an AI GM runs
    Samurai, who went 1-1 against her."""
    league = factory.league(state="offseason")
    code = uuid.uuid4().hex[:6].upper()
    _set(db_conn, league, name="Weekend League", join_code=code)
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="Amsterdam", mascot="Captains")
    theirs = factory.team(city="Tokyo", mascot="Samurai")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    alice, alice_user = _person(db_conn, factory, league, "Alice", mine)
    ai = factory.gm(team=theirs, league=league)
    db_conn.execute("UPDATE gms SET display_name = 'Robo' WHERE id = %s", (ai.id,))
    _game(db_conn, season, mine, theirs)
    _game(db_conn, season, theirs, mine)
    return {
        "league": league,
        "season": season,
        "mine": mine,
        "theirs": theirs,
        "alice": alice,
        "alice_user": alice_user,
        "ai": ai,
        "code": code,
    }


def _league(db, league):
    return db.execute("SELECT * FROM leagues WHERE id = %s", (league.id,)).fetchone()


class TestWhenOpen:
    def test_open_between_seasons(self, db_conn, setup):
        for state in takeover.BETWEEN_SEASONS:
            _set(db_conn, setup["league"], state=state)
            assert (
                takeover.closed_reason(db_conn, _league(db_conn, setup["league"]))
                is None
            )

    @pytest.mark.parametrize("state", ["season", "playoffs", "complete"])
    def test_closed_during_a_season(self, db_conn, setup, state):
        _set(db_conn, setup["league"], state=state)
        assert takeover.closed_reason(db_conn, _league(db_conn, setup["league"]))

    def test_commissioner_can_close_it(self, db_conn, setup):
        _set(db_conn, setup["league"], late_joins=False)
        reason = takeover.closed_reason(db_conn, _league(db_conn, setup["league"]))
        assert "isn't taking new GMs" in reason

    def test_closed_with_no_ai_teams(self, db_conn, setup):
        db_conn.execute("DELETE FROM gms WHERE id = %s", (setup["ai"].id,))
        reason = takeover.closed_reason(db_conn, _league(db_conn, setup["league"]))
        assert "already has a person" in reason

    def test_open_teams_lists_ai_teams_with_last_season(self, db_conn, setup):
        teams = takeover.open_teams(db_conn, setup["league"].id)
        assert [t["team_id"] for t in teams] == [setup["theirs"].id]
        assert teams[0]["last_wl"] == {"w": 1, "l": 1}


class TestTakeOver:
    def test_ai_row_becomes_the_person(self, db_conn, setup):
        bob = _user(db_conn, "Bob")
        gm_id = takeover.take_over(db_conn, setup["league"].id, bob, setup["theirs"].id)
        assert gm_id == setup["ai"].id
        row = _gm(db_conn, gm_id)
        assert not row["is_ai"]
        assert row["user_id"] == bob["id"]
        assert row["display_name"] == "Bob"
        assert row["persona_id"] is None
        assert row["team_id"] == setup["theirs"].id
        # The offseason before 2026: their record starts in 2026.
        assert row["joined_year"] == 2026
        assert GMRepository(db_conn).get_human_team_ids(setup["league"].id) == {
            setup["mine"].id,
            setup["theirs"].id,
        }

    def test_old_owner_messages_dont_come_with_the_team(self, db_conn, setup):
        # The owner wrote to the AI GM all season; none of it is the new GM's.
        for n in range(3):
            db_conn.execute(
                """INSERT INTO owner_messages
                       (league_id, team_id, gm_id, season_id, key, kind, body)
                   VALUES (%s, %s, %s, %s, %s, 'checkin', 'Old news.')""",
                (
                    setup["league"].id,
                    setup["theirs"].id,
                    setup["ai"].id,
                    setup["season"].id,
                    f"check:{setup['season'].id}:{n}",
                ),
            )
        bob = _user(db_conn, "Bob")
        gm_id = takeover.take_over(db_conn, setup["league"].id, bob, setup["theirs"].id)
        assert owner_office.unseen(db_conn, gm_id) == 0
        office = owner_office.office(
            db_conn, setup["league"].id, setup["theirs"].id, gm_id
        )
        assert office["messages"] == []

    def test_draft_state_starts_with_the_new_season(self, db_conn, factory, setup):
        new = factory.season(year=2026)
        factory.league_season(setup["league"], new)
        _set(db_conn, setup["league"], state="draft")
        gm_id = takeover.take_over(
            db_conn, setup["league"].id, _user(db_conn, "Bob"), setup["theirs"].id
        )
        assert _gm(db_conn, gm_id)["joined_year"] == 2026

    def test_refused_mid_season(self, db_conn, setup):
        _set(db_conn, setup["league"], state="season")
        with pytest.raises(takeover.TakeoverClosed):
            takeover.take_over(
                db_conn, setup["league"].id, _user(db_conn, "Bob"), setup["theirs"].id
            )
        assert _gm(db_conn, setup["ai"].id)["is_ai"]

    def test_refused_for_a_human_team(self, db_conn, setup):
        with pytest.raises(takeover.TakeoverClosed):
            takeover.take_over(
                db_conn, setup["league"].id, _user(db_conn, "Bob"), setup["mine"].id
            )

    def test_refused_for_someone_already_in_it(self, db_conn, setup):
        with pytest.raises(takeover.TakeoverClosed):
            takeover.take_over(
                db_conn, setup["league"].id, setup["alice_user"], setup["theirs"].id
            )


class TestCareer:
    def test_seasons_before_the_takeover_dont_count(self, db_conn, setup):
        bob = _user(db_conn, "Bob")
        takeover.take_over(db_conn, setup["league"].id, bob, setup["theirs"].id)
        career.record_league(db_conn, setup["league"].id)
        repo = CareerRepository(db_conn)
        assert repo.for_user(bob["id"]) == []
        # Alice's 2025 still counts, but not as games against Bob.
        assert len(repo.for_user(setup["alice_user"]["id"])) == 1
        h2h = db_conn.execute(
            "SELECT * FROM gm_head_to_head WHERE user_id = %s OR opponent_id = %s",
            (bob["id"], bob["id"]),
        ).fetchall()
        assert h2h == []


@pytest.fixture
def client(db_conn):
    app.dependency_overrides[get_db] = lambda: db_conn
    yield
    app.dependency_overrides.clear()


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: {
        **user,
        "has_password": True,
        "is_admin": False,
    }
    return TestClient(app)


class TestPages:
    def test_join_code_goes_to_team_picker(self, db_conn, setup, client):
        c = _as(_user(db_conn, "Bob"))
        r = c.post(
            "/leagues/join",
            data={"join_code": setup["code"].lower()},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"].endswith(f"/take-over?code={setup['code']}")
        page = c.get(r.headers["location"])
        assert "Tokyo Samurai" in page.text
        assert "Amsterdam Captains" not in page.text

    def test_team_picker_sorts_by_team_or_record(self, db_conn, setup, client):
        c = _as(_user(db_conn, "Bob"))
        page = c.get(
            f"/leagues/{setup['league'].id}/take-over?code={setup['code']}"
        ).text
        assert "data-sortable" in page
        assert '<th data-sort="text">Team</th>' in page
        assert 'data-sort="num" data-sort-first="desc"' in page
        assert 'data-sort-value="Tokyo Samurai"' in page
        # 1-1 last season: .5 win share plus a tiny wins tiebreak.
        assert 'data-sort-value="0.500010"' in page

    def test_join_code_mid_season_explains(self, db_conn, setup, client):
        _set(db_conn, setup["league"], state="season")
        c = _as(_user(db_conn, "Bob"))
        r = c.post("/leagues/join", data={"join_code": setup["code"]})
        assert "between seasons" in r.text

    def test_private_league_needs_the_code(self, db_conn, setup, client):
        c = _as(_user(db_conn, "Bob"))
        r = c.get(f"/leagues/{setup['league'].id}/take-over", follow_redirects=False)
        assert r.headers["location"].endswith(f"cant_join={setup['league'].id}")
        r = c.post(
            f"/leagues/{setup['league'].id}/take-over",
            data={"team_id": setup["theirs"].id},
            follow_redirects=False,
        )
        assert _gm(db_conn, setup["ai"].id)["is_ai"]

    def test_take_over_by_post(self, db_conn, setup, client):
        bob = _user(db_conn, "Bob")
        c = _as(bob)
        r = c.post(
            f"/leagues/{setup['league'].id}/take-over",
            data={"team_id": setup["theirs"].id, "code": setup["code"]},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert _gm(db_conn, setup["ai"].id)["user_id"] == bob["id"]

    def test_commissioner_flips_settings(self, db_conn, setup, client):
        GMRepository(db_conn).set_commissioner(setup["alice"].id, setup["league"].id)
        c = _as(setup["alice_user"])
        lid = setup["league"].id
        r = c.post(
            f"/leagues/{lid}/settings/is_public",
            data={"on": "true", "next": f"/leagues/{lid}/league"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == f"/leagues/{lid}/league"
        c.post(f"/leagues/{lid}/settings/late_joins", data={"on": "false"})
        league = _league(db_conn, setup["league"])
        assert league["is_public"] and not league["late_joins"]

    def test_only_the_commissioner_flips_settings(self, db_conn, setup, client):
        c = _as(setup["alice_user"])  # not commissioner
        r = c.post(
            f"/leagues/{setup['league'].id}/settings/is_public", data={"on": "true"}
        )
        assert r.status_code == 403
        r2 = c.post(f"/leagues/{setup['league'].id}/settings/name", data={"on": "true"})
        assert r2.status_code == 403
        assert not _league(db_conn, setup["league"])["is_public"]

    def test_public_league_on_join_tab(self, db_conn, setup, client):
        _set(db_conn, setup["league"], is_public=True)
        c = _as(_user(db_conn, "Bob"))
        r = c.get("/leagues/?tab=join")
        assert "Weekend League" in r.text
        assert "Pick a team" in r.text


class TestLandingAfterTakeOver:
    """Wherever between seasons a person takes over, coming into the league
    takes them to the right page, never the lobby, and on to their season
    preview."""

    def _joined(self, db_conn, setup, state, draft_state=None):
        """Move the league to `state` and have Bob take over the Samurai.
        From the draft on, the 2026 season and its draft exist."""
        league = setup["league"]
        if state != "offseason":
            self.next_season = self.factory.season(year=2026)
            self.factory.draft(
                league=league, season=self.next_season, state=draft_state or "pending"
            )
        _set(db_conn, league, state=state)
        bob = _user(db_conn, "Bob")
        takeover.take_over(db_conn, league.id, bob, setup["theirs"].id)
        return _as(bob)

    @pytest.fixture(autouse=True)
    def _factory(self, factory):
        self.factory = factory

    def _home(self, c, setup):
        r = c.get(f"/leagues/{setup['league'].id}/", follow_redirects=False)
        assert r.status_code in (302, 307), "landed on the lobby"
        return r.headers["location"]

    def test_offseason_goes_to_the_season_summary(self, db_conn, setup, client):
        c = self._joined(db_conn, setup, "offseason")
        assert self._home(c, setup).endswith("/season-summary")
        page = c.get(f"/leagues/{setup['league'].id}/season-summary")
        assert "taken over the Tokyo Samurai" in page.text
        assert "2026 season preview" in page.text

    def test_people_already_in_it_land_on_the_summary_too(self, db_conn, setup, client):
        c = _as(setup["alice_user"])
        assert self._home(c, setup).endswith("/season-summary")
        page = c.get(f"/leagues/{setup['league'].id}/season-summary")
        assert "taken over" not in page.text

    def test_before_the_draft_goes_to_the_preview(self, db_conn, setup, client):
        c = self._joined(db_conn, setup, "draft")
        assert self._home(c, setup).endswith("/welcome")

    @pytest.mark.parametrize("state", ["draft", "preseason"])
    def test_after_the_draft_goes_to_the_preview(self, db_conn, setup, client, state):
        c = self._joined(db_conn, setup, state, draft_state="complete")
        assert self._home(c, setup).endswith("/welcome")

    def test_after_the_preview_the_draft_results(self, db_conn, setup, client):
        c = self._joined(db_conn, setup, "preseason", draft_state="complete")
        GMRepository(db_conn).mark_welcomed(setup["ai"].id, self.next_season.id)
        assert self._home(c, setup).endswith("/draft/results")
