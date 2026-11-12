# tests/api/web/test_settings_votes.py
"""
In a league with more than one person, the commissioner proposes settings
changes and the other human GMs vote (src/api/services/settings_votes.py):
one Reject sinks it, it passes once everyone approves or after two decision
windows, and not voting counts as approval.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import settings_votes
from src.api.services.injury_news import take_injury_news
from src.db.repositories.league_repo import LeagueRepository


@pytest.fixture
def league(db_conn, factory):
    """Season 2 of 10 with three human GMs (the first is commissioner) and
    one AI GM, in decision window 5."""
    lg = factory.league(state="season", trades_enabled=True)
    db_conn.execute(
        "UPDATE leagues SET num_teams = 4, num_seasons = 10, sim_period_days = 3,"
        " pace_control = 'timer', sim_period = 5 WHERE id = %s",
        (lg.id,),
    )
    for y in (2025, 2026):
        factory.league_season(lg, factory.season(year=y))
    gms = [
        factory.gm(team=factory.team(city=c, mascot=m), league=lg, is_ai=False)
        for c, m in (("Boston", "Beans"), ("Denver", "Peaks"), ("Austin", "Bats"))
    ]
    for g, name in zip(gms, ("Commish", "Dee", "Al")):
        db_conn.execute("UPDATE gms SET display_name = %s WHERE id = %s", (name, g.id))
    factory.gm(team=factory.team(city="Chicago", mascot="Wind"), league=lg)
    db_conn.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gms[0].id, lg.id)
    )
    return lg, gms


@pytest.fixture
def as_gm(db_conn):
    """A client acting as the given GM."""

    def make(gm):
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        app.dependency_overrides[get_current_gm] = lambda: {"id": gm.id}
        app.dependency_overrides[get_gm_or_viewer] = lambda: {
            "id": gm.id,
            "team_id": None,
        }
        return TestClient(app, follow_redirects=False)

    yield make
    app.dependency_overrides.clear()


def _form(**overrides):
    form = {
        "name": "Test League",
        "num_seasons": "10",
        "pace_control": "timer",
        "decision_window_sec": "120",
        "draft_window_sec": "300",
        "lineup_window_sec": "600",
        "sim_period_days": "3",
        "weighted_schedule": "false",
        "injuries_enabled": "true",
        "trades_enabled": "true",
        "trade_vote": "true",
        "pick_trades": "false",
        "reentry_enabled": "false",
    }
    form.update(overrides)
    return {k: v for k, v in form.items() if v is not None}


def _row(db_conn, lg):
    return LeagueRepository(db_conn).get_by_id(lg.id)


def _propose(as_gm, league, **changes):
    lg, gms = league
    return as_gm(gms[0]).post(
        f"/leagues/{lg.id}/league/settings/propose", data=_form(**changes)
    )


def _vote(as_gm, league, who, yes):
    lg, gms = league
    return as_gm(gms[who]).post(
        f"/leagues/{lg.id}/league/settings/vote",
        data={"yes": "true" if yes else "false"},
    )


def _status(db_conn, lg):
    row = db_conn.execute(
        "SELECT status FROM settings_proposals WHERE league_id = %s"
        " ORDER BY created_at DESC LIMIT 1",
        (lg.id,),
    ).fetchone()
    return row and row["status"]


def test_commissioner_proposes_only_what_changed(as_gm, db_conn, league):
    lg, gms = league
    html = as_gm(gms[0]).get(f"/leagues/{lg.id}/league").text
    assert ">Propose changes</button>" in html
    assert 'name="pace_control"' in html and 'name="trade_vote"' in html
    assert (
        ">Propose changes</button>"
        not in as_gm(gms[1]).get(f"/leagues/{lg.id}/league").text
    )

    r = _propose(as_gm, league, pace_control="confirmed", sim_period_days="5")

    assert r.headers["location"].endswith("?saved=proposed")
    proposal = settings_votes.open_proposal(db_conn, lg.id)
    assert proposal["changes"] == {
        "pace_control": {"old": "timer", "new": "confirmed"},
        "sim_period_days": {"old": 3, "new": 5},
    }
    # Two whole windows after this one.
    assert proposal["closes_period"] == 7
    assert sorted(v["display_name"] for v in proposal["votes"]) == ["Al", "Dee"]
    # Nothing changes until it passes.
    assert _row(db_conn, lg)["pace_control"] == "timer"


def test_voters_hear_about_it_and_see_the_vote(as_gm, db_conn, league):
    lg, gms = league
    _propose(as_gm, league, pace_control="confirmed")

    news = take_injury_news(db_conn, gms[1].id)["settings"]
    assert news[0]["event"] == "proposed"
    assert "Pace Confirmed" in news[0]["text"]
    assert take_injury_news(db_conn, gms[0].id)["settings"] == []

    html = as_gm(gms[1]).get(f"/leagues/{lg.id}/league").text
    assert 'id="settings-vote"' in html
    assert ">Approve</button>" in html and ">Reject</button>" in html
    commish = as_gm(gms[0]).get(f"/leagues/{lg.id}/league").text
    assert ">Withdraw proposal</button>" in commish


def test_one_reject_sinks_it(as_gm, db_conn, league):
    lg, gms = league
    _propose(as_gm, league, pace_control="confirmed")
    _vote(as_gm, league, 1, True)

    _vote(as_gm, league, 2, False)

    assert _status(db_conn, lg) == "rejected"
    assert _row(db_conn, lg)["pace_control"] == "timer"
    news = take_injury_news(db_conn, gms[0].id)["settings"]
    assert "Al rejected" in news[-1]["text"]


def test_passes_once_everyone_approves(as_gm, db_conn, league):
    lg, gms = league
    _propose(as_gm, league, pace_control="confirmed", injuries_enabled=None)

    _vote(as_gm, league, 1, True)
    assert _status(db_conn, lg) == "open"
    _vote(as_gm, league, 2, True)

    assert _status(db_conn, lg) == "passed"
    row = _row(db_conn, lg)
    assert row["pace_control"] == "confirmed"
    assert row["injuries_enabled"] is False
    news = take_injury_news(db_conn, gms[1].id)["settings"]
    assert news[-1]["event"] == "passed"


def test_not_voting_counts_as_approval_after_two_windows(as_gm, db_conn, league):
    lg, _ = league
    _propose(as_gm, league, name="New Name")
    _vote(as_gm, league, 1, True)

    settings_votes.close_due(db_conn, lg.id, 6)
    assert _status(db_conn, lg) == "open"

    settings_votes.close_due(db_conn, lg.id, 7)
    assert _status(db_conn, lg) == "passed"
    assert _row(db_conn, lg)["name"] == "New Name"


def test_one_proposal_at_a_time_and_something_must_change(as_gm, db_conn, league):
    lg, _ = league
    r = _propose(as_gm, league)
    assert (
        "Nothing+changed" in r.headers["location"]
        or "Nothing%20changed" in r.headers["location"]
    )

    _propose(as_gm, league, pace_control="confirmed")
    r = _propose(as_gm, league, sim_period_days="9")
    assert "settings_error=" in r.headers["location"]


def test_bad_values_are_refused(as_gm, db_conn, league):
    lg, _ = league
    r = _propose(as_gm, league, num_seasons="1")
    assert "settings_error=" in r.headers["location"]
    assert settings_votes.open_proposal(db_conn, lg.id) is None


def test_commissioner_withdraws(as_gm, db_conn, league):
    lg, gms = league
    _propose(as_gm, league, pace_control="confirmed")

    as_gm(gms[0]).post(f"/leagues/{lg.id}/league/settings/withdraw")

    assert _status(db_conn, lg) == "withdrawn"
    # A voter can't vote on it any more.
    r = _vote(as_gm, league, 1, True)
    assert "settings_error=" in r.headers["location"]


def test_only_the_commissioner_proposes(as_gm, db_conn, league):
    lg, gms = league
    as_gm(gms[1]).post(
        f"/leagues/{lg.id}/league/settings/propose",
        data=_form(pace_control="confirmed"),
    )
    assert settings_votes.open_proposal(db_conn, lg.id) is None


def test_injury_rate_goes_to_a_vote(as_gm, db_conn, league):
    lg, gms = league

    _propose(as_gm, league, injury_rate="200")

    proposal = settings_votes.open_proposal(db_conn, lg.id)
    assert proposal["changes"] == {"injury_rate": {"old": 100, "new": 200}}
    assert settings_votes.describe(proposal["changes"])[0]["new"] == "200%"


def test_injury_rate_off_the_steps_cant_be_proposed(as_gm, db_conn, league):
    lg, _ = league

    r = _propose(as_gm, league, injury_rate="150")

    assert "settings_error=" in r.headers["location"]
    assert settings_votes.open_proposal(db_conn, lg.id) is None
