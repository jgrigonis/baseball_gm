# tests/api/test_firing.py
"""Owners firing GMs (src/api/services/firing.py): the review's verdict, an
AI GM replaced by a new persona, a fired person watching, and re-entry
through taking over another team (takeover.py)."""

import uuid

import pytest

from src.api.dependencies import NotLeagueGM, get_current_gm, get_gm_or_viewer
from src.api.services import firing, owner_review, takeover
from src.api.services import owners as owner_service
from src.api.services.news.events import firings as firing_news
from src.api.services.news.names import Names, plain
from src.db.repositories.owner_repo import OwnerRepository
from src.league import owner_scoring as sc
from src.league import owners


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


def _set(db, league_id, **cols):
    for col, val in cols.items():
        db.execute(f"UPDATE leagues SET {col} = %s WHERE id = %s", (val, league_id))


def _league(db, league_id):
    return dict(
        db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
    )


def _gm(db, gm_id):
    row = db.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()
    return dict(row) if row else None


@pytest.fixture
def lg(db_conn, factory):
    """A league just done with its 2026 season: Alice runs the Captains, AI
    GMs the Samurai and the Owls. Firing is on, re-entry too."""
    league = factory.league(state="offseason")
    _set(
        db_conn, league.id, name="Test League", owner_firing=True,
        reentry_enabled=True, late_joins=False, mode="blitz",
    )  # fmt: skip
    season = factory.season(year=2026)
    factory.league_season(league, season)
    teams = [
        factory.team(city=c, mascot=m)
        for c, m in (("Amsterdam", "Captains"), ("Tokyo", "Samurai"), ("Oslo", "Owls"))
    ]
    for t in teams:
        factory.league_season_team(league, season, t)
    alice = factory.gm(team=teams[0], league=league, is_ai=False)
    user = _user(db_conn, "Alice")
    db_conn.execute(
        "UPDATE gms SET user_id = %s, display_name = 'Alice' WHERE id = %s",
        (user["id"], alice.id),
    )
    _set(db_conn, league.id, commissioner_gm_id=alice.id)
    ai = factory.gm(team=teams[1], league=league)
    other = factory.gm(team=teams[2], league=league)
    for g, name in ((ai, "Robo"), (other, "Botty")):
        db_conn.execute("UPDATE gms SET display_name = %s WHERE id = %s", (name, g.id))
    owner_service.ensure(db_conn, league.id)

    class X:
        pass

    x = X()
    x.db, x.league, x.season, x.teams = db_conn, league, season, teams
    x.alice, x.user, x.ai, x.other = alice.id, user, ai.id, other.id
    return x


def _fire(x, gm_id, wins=60, losses=102):
    x.db.execute(
        """INSERT INTO gm_season_evaluations
               (gm_id, season_id, wins, losses, verdict, score, job_security, detail)
           VALUES (%s, %s, %s, %s, 'fired', -0.9, 5, '{}')""",
        (gm_id, x.season.id, wins, losses),
    )
    x.db.execute(
        """INSERT INTO owner_messages (league_id, team_id, gm_id, season_id, key,
               kind, body, created_on)
           SELECT g.league_id, g.team_id, g.id, %s, 'review:x', 'review',
                  'You''re fired.', '2026-10-31'
           FROM gms g WHERE g.id = %s""",
        (x.season.id, gm_id),
    )


class TestTheReview:
    def _bad_season(self, x, monkeypatch, tenure_seasons=3):
        """Every owner hates the season, and Alice was on the hot seat
        under her owner for the seasons before."""
        monkeypatch.setattr(sc, "season_score", lambda scores, weights: -1.0)
        owner = owner_service.ensure(x.db, x.league.id)[x.teams[0].id]
        x.db.execute(
            "UPDATE team_owners SET since_year = 2020 WHERE league_id = %s",
            (x.league.id,),
        )
        for i in range(tenure_seasons):
            past = x.db.execute(
                "INSERT INTO seasons (id, year) VALUES (%s, %s) RETURNING id",
                (_id(), 2025 - i),
            ).fetchone()["id"]
            x.db.execute(
                """INSERT INTO gm_season_evaluations
                       (gm_id, season_id, verdict, owner_id, score, job_security,
                        detail)
                   VALUES (%s, %s, 'warned', %s, -0.5, 20, %s)""",
                (
                    x.alice, past, owner["owner_id"],
                    f'{{"who": "{x.user["id"]}"}}',
                ),
            )  # fmt: skip

    def test_fired_when_the_league_fires(self, lg, monkeypatch):
        self._bad_season(lg, monkeypatch)
        out = owner_review.review_season(lg.db, lg.league.id, lg.season.id, 2026)
        assert out[lg.teams[0].id]["verdict"] == "fired"
        # The AI GMs are new to their owners: the honeymoon holds them back.
        assert out[lg.teams[1].id]["verdict"] != "fired"

    def test_only_warned_with_firing_off(self, lg, monkeypatch):
        _set(lg.db, lg.league.id, owner_firing=False)
        self._bad_season(lg, monkeypatch)
        out = owner_review.review_season(lg.db, lg.league.id, lg.season.id, 2026)
        assert out[lg.teams[0].id]["verdict"] == "warned"
        row = lg.db.execute(
            "SELECT detail FROM gm_season_evaluations WHERE gm_id = %s AND season_id = %s",
            (lg.alice, lg.season.id),
        ).fetchone()
        assert row["detail"]["would_fire"]

    def test_never_in_speed_blitz(self, lg, monkeypatch):
        _set(lg.db, lg.league.id, mode="speed_blitz")
        self._bad_season(lg, monkeypatch)
        out = owner_review.review_season(lg.db, lg.league.id, lg.season.id, 2026)
        assert out[lg.teams[0].id]["verdict"] != "fired"


class TestAnAIGM:
    def test_replaced_by_a_new_persona(self, lg):
        before = _gm(lg.db, lg.ai)
        _fire(lg, lg.ai)
        done = firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026)
        assert [f["gm_id"] for f in done] == [lg.ai]
        after = _gm(lg.db, lg.ai)
        assert after["team_id"] == lg.teams[1].id and after["is_ai"]
        assert after["display_name"] != before["display_name"]
        row = lg.db.execute(
            "SELECT * FROM gm_firings WHERE gm_id = %s", (lg.ai,)
        ).fetchone()
        assert row["display_name"] == "Robo" and row["user_id"] is None
        assert row["wins"] == 60 and row["message"] == "You're fired."
        # Running it again fires nobody twice.
        assert firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026) == []

    def test_the_news(self, lg):
        _fire(lg, lg.ai)
        firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026)
        firing_news(
            lg.db, Names(lg.db, lg.league.id), lg.league.id, lg.season.id, "2026-10-31"
        )
        story = lg.db.execute(
            "SELECT headline, body FROM league_news WHERE league_id = %s",
            (lg.league.id,),
        ).fetchone()
        assert plain(story["headline"]) == "Samurai fire GM Robo"
        assert "60-102" in plain(story["body"])


class TestAPerson:
    def test_fired_person_watches(self, lg):
        _fire(lg, lg.alice)
        firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026)
        # The team's row went to an AI GM, with its history.
        team_row = _gm(lg.db, lg.alice)
        assert team_row["is_ai"] and team_row["user_id"] is None
        assert team_row["team_id"] == lg.teams[0].id
        # The owner's messages were to Alice, not the new GM.
        assert not lg.db.execute(
            "SELECT 1 FROM owner_messages WHERE gm_id = %s", (lg.alice,)
        ).fetchone()
        # Alice has a fired row with no team: a viewer.
        mine = lg.db.execute(
            "SELECT * FROM gms WHERE league_id = %s AND user_id = %s",
            (lg.league.id, lg.user["id"]),
        ).fetchone()
        assert mine["fired_at"] and mine["team_id"] is None
        user = {"id": lg.user["id"], "display_name": "Alice"}
        viewer = get_gm_or_viewer(lg.league.id, lg.db, user)
        assert viewer["is_viewer"] and viewer["fired"] and viewer["id"] is None
        with pytest.raises(NotLeagueGM):
            get_current_gm(lg.league.id, lg.db, user)
        info = firing.latest(lg.db, lg.league.id, lg.user["id"])
        assert info["mascot"] == "Captains" and info["message"] == "You're fired."
        # Re-entry, with nobody else around: the commissioner role waits on
        # her fired row.
        assert _league(lg.db, lg.league.id)["commissioner_gm_id"] == mine["id"]
        assert not firing.nobody_left(lg.db, lg.league.id)

    def test_re_entry_takes_another_ai_team(self, lg):
        _fire(lg, lg.alice)
        firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026)
        league = _league(lg.db, lg.league.id)
        uid = lg.user["id"]
        # Open to her even with late joiners off, but not her old team.
        assert takeover.closed_reason(lg.db, league, uid) is None
        assert takeover.closed_reason(lg.db, league)  # others: closed
        teams = {t["team_id"] for t in takeover.open_teams(lg.db, lg.league.id, uid)}
        assert teams == {lg.teams[1].id, lg.teams[2].id}
        with pytest.raises(takeover.TakeoverClosed):
            takeover.take_over(lg.db, lg.league.id, lg.user, lg.teams[0].id)
        gm_id = takeover.take_over(lg.db, lg.league.id, lg.user, lg.teams[2].id)
        assert gm_id == lg.other
        rows = lg.db.execute(
            "SELECT * FROM gms WHERE league_id = %s AND user_id = %s",
            (lg.league.id, uid),
        ).fetchall()
        assert len(rows) == 1 and rows[0]["id"] == lg.other
        assert rows[0]["fired_at"] is None and not rows[0]["is_ai"]
        assert _league(lg.db, lg.league.id)["commissioner_gm_id"] == lg.other
        f = firing.latest(lg.db, lg.league.id, uid)
        assert f["rehired_team_id"] == lg.teams[2].id

    def test_one_and_done(self, lg):
        _set(lg.db, lg.league.id, reentry_enabled=False)
        _fire(lg, lg.alice)
        firing.carry_out(lg.db, lg.league.id, lg.season.id, 2026)
        league = _league(lg.db, lg.league.id)
        assert "one and done" in takeover.closed_reason(lg.db, league, lg.user["id"])
        # Nobody runs a team any more: the league is over.
        assert firing.nobody_left(lg.db, lg.league.id)
        assert league["commissioner_gm_id"] is None


def test_owner_rules_by_archetype_exist_for_real_archetypes():
    names = {a.name for a in owners.ARCHETYPES}
    assert set(sc.FIRING_RULES) <= names
    assert OwnerRepository  # imported for seat() in other tests
