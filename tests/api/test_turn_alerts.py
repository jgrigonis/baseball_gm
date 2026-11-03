# tests/api/test_turn_alerts.py
"""A multiplayer league moves on with nobody watching, and emails the GMs it's
waiting on who aren't looking (src/api/services/turn_alerts.py)."""

from unittest.mock import patch

import pytest

from src.api.services import ready_check, turn_alerts
from tests.api.test_ready_check import _expire_window, _league, _period


@pytest.fixture
def run_period():
    with patch.object(ready_check, "_run_period") as run:
        run.return_value = False
        yield run


@pytest.fixture
def sent():
    """The emails that would have gone out."""
    out = []
    with patch.object(turn_alerts, "_send_in_background", side_effect=out.extend):
        yield out


def _addr(gm):
    # Unique across tests: the tests commit, and emails are unique.
    return f"{gm.id}@example.com"


def _emails(db, gms):
    for gm in gms:
        db.execute(
            "UPDATE users SET email = %s WHERE id = (SELECT user_id FROM gms WHERE id = %s)",
            (_addr(gm), gm.id),
        )


def _everyone_ready(db, league, gms):
    for gm in gms:
        ready_check.set_ready(db, league.id, gm.id, True)
    assert ready_check.advance_if_due(db, league.id)


class TestEmails:
    def test_emails_each_gm_not_looking(self, db_conn, factory, run_period, sent):
        league, gms = _league(db_conn, factory, window=3600)
        _emails(db_conn, gms)
        _everyone_ready(db_conn, league, gms)
        assert sorted(to for to, _, _ in sent) == sorted(_addr(g) for g in gms)
        to, subject, text = sent[0]
        assert subject == "Your move in Test League"
        assert f"/leagues/{league.id}/" in text
        assert "about 60 minutes" in text

    def test_not_while_the_page_is_open(self, db_conn, factory, run_period, sent):
        league, (a, b) = _league(db_conn, factory, window=3600)
        _emails(db_conn, (a, b))
        turn_alerts.mark_seen(db_conn, a.id)
        _everyone_ready(db_conn, league, (a, b))
        assert [to for to, _, _ in sent] == [_addr(b)]

    def test_once_per_absence(self, db_conn, factory, run_period, sent):
        league, (a, b) = _league(db_conn, factory, window=3600)
        _emails(db_conn, (a,))
        _everyone_ready(db_conn, league, (a, b))
        assert len(sent) == 1
        # The clock runs out again with a still away: no second email.
        _expire_window(db_conn, league)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert len(sent) == 1
        # a comes back, then leaves: the next period emails them again.
        db_conn.execute(
            "UPDATE gms SET alerted_at = NOW() - INTERVAL '10 minutes',"
            " seen_at = NOW() - INTERVAL '5 minutes' WHERE id = %s",
            (a.id,),
        )
        _expire_window(db_conn, league)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert len(sent) == 2

    def test_short_windows_send_nothing(self, db_conn, factory, run_period, sent):
        league, gms = _league(db_conn, factory, window=120)
        _emails(db_conn, gms)
        _everyone_ready(db_conn, league, gms)
        assert sent == []

    def test_confirmed_pace_has_no_clock(self, db_conn, factory, run_period, sent):
        league, (a, b) = _league(db_conn, factory, pace="confirmed")
        _emails(db_conn, (a,))
        gms = (a, b)
        _everyone_ready(db_conn, league, gms)
        assert len(sent) == 1
        assert "until everyone clicks Ready" in sent[0][2]

    def test_turned_off_or_no_email(self, db_conn, factory, run_period, sent):
        league, (a, b) = _league(db_conn, factory, window=3600)
        _emails(db_conn, (a,))
        db_conn.execute(
            "UPDATE users SET turn_emails = FALSE"
            " WHERE id = (SELECT user_id FROM gms WHERE id = %s)",
            (a.id,),
        )
        _everyone_ready(db_conn, league, (a, b))
        assert sent == []

    def test_away_gm_gets_nothing(self, db_conn, factory, run_period, sent):
        league, (a, b) = _league(db_conn, factory, window=3600)
        _emails(db_conn, (a, b))
        ready_check.set_away(db_conn, b.id, True)
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert [to for to, _, _ in sent] == [_addr(a)]


class TestClock:
    # Other tests leave leagues behind, so these look at their own league
    # rather than how many the clock moved on.
    def test_moves_on_an_expired_league(self, db_conn, factory, run_period, sent):
        league, _ = _league(db_conn, factory)
        ready_check.advance_if_due(db_conn, league.id)  # opens the window
        turn_alerts.advance_due_leagues(db_conn)
        assert _period(db_conn, league)["sim_period"] == 0
        _expire_window(db_conn, league)
        turn_alerts.advance_due_leagues(db_conn)
        assert _period(db_conn, league)["sim_period"] == 1

    def test_opens_a_window_nobody_has_looked_at(
        self, db_conn, factory, run_period, sent
    ):
        league, _ = _league(db_conn, factory, window=90)
        turn_alerts.advance_due_leagues(db_conn)
        assert _period(db_conn, league)["period_deadline"] is not None
        assert _period(db_conn, league)["sim_period"] == 0

    def test_leaves_paused_and_single_player_leagues(
        self, db_conn, factory, run_period, sent
    ):
        paused, _ = _league(db_conn, factory)
        solo, _ = _league(db_conn, factory, humans=1)
        db_conn.execute(
            "UPDATE leagues SET is_paused = TRUE WHERE id = %s", (paused.id,)
        )
        for league in (paused, solo):
            _expire_window(db_conn, league)
        turn_alerts.advance_due_leagues(db_conn)
        for league in (paused, solo):
            assert _period(db_conn, league)["sim_period"] == 0
