# tests/api/test_ready_check.py
"""A multiplayer league sims its next period when every GM who isn't away is
ready, or, under timer pace, when the Decision Window runs out."""

import os
import uuid
from unittest.mock import patch

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

from src.api.dependencies import require_single_player
from src.api.services import ready_check
from src.db.locks import league_lock


@pytest.fixture
def run_period():
    """Stands in for the sim itself; these tests are about when it runs."""
    with patch.object(ready_check, "_run_period") as run:
        yield run


def _league(db, factory, humans=2, state="season", pace="timer", window=120):
    league = factory.league(state=state)
    db.execute(
        "UPDATE leagues SET pace_control = %s, decision_window_sec = %s WHERE id = %s",
        (pace, window, league.id),
    )
    gms = []
    for i in range(humans):
        gm = factory.gm(league=league, is_ai=False)
        user_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
            (user_id, user_id, f"GM {i}"),
        )
        db.execute(
            "UPDATE gms SET user_id = %s, display_name = %s WHERE id = %s",
            (user_id, f"GM {i}", gm.id),
        )
        gms.append(gm)
    factory.gm(league=league, is_ai=True)
    return league, gms


def _expire_window(db, league):
    db.execute(
        "UPDATE leagues SET period_deadline = NOW() - INTERVAL '1 second' WHERE id = %s",
        (league.id,),
    )


def _period(db, league):
    return db.execute(
        "SELECT sim_period, period_deadline FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()


class TestWhoCounts:
    def test_one_human_is_single_player(self, db_conn, factory):
        league, _ = _league(db_conn, factory, humans=1)
        assert not ready_check.is_multiplayer(db_conn, league.id)
        require_single_player(league.id, db_conn)  # no error

    def test_two_humans_are_multiplayer(self, db_conn, factory):
        league, _ = _league(db_conn, factory, humans=2)
        assert ready_check.is_multiplayer(db_conn, league.id)
        with pytest.raises(HTTPException) as e:
            require_single_player(league.id, db_conn)
        assert e.value.status_code == 403

    def test_fired_gm_doesnt_count(self, db_conn, factory):
        league, (a, b) = _league(db_conn, factory, humans=2)
        db_conn.execute("UPDATE gms SET fired_at = NOW() WHERE id = %s", (b.id,))
        assert not ready_check.is_multiplayer(db_conn, league.id)


class TestTimerPace:
    def test_runs_when_everyone_is_ready(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory)
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_not_called()

        ready_check.set_ready(db_conn, league.id, b.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_called_once_with(db_conn, league.id, "season", 3)
        assert _period(db_conn, league)["sim_period"] == 1

    def test_next_period_starts_everyone_unready(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory)
        for gm in (a, b):
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        ready_check.advance_if_due(db_conn, league.id)

        status = ready_check.status(db_conn, league.id, a.id)
        assert status["period"] == 1
        assert not status["you_ready"]
        assert status["waiting_on"] == ["GM 0", "GM 1"]

    def test_opens_the_window_on_first_look(self, db_conn, factory, run_period):
        league, (a, _) = _league(db_conn, factory, window=90)
        assert _period(db_conn, league)["period_deadline"] is None
        ready_check.advance_if_due(db_conn, league.id)
        status = ready_check.status(db_conn, league.id, a.id)
        assert 85 <= status["seconds_left"] <= 90

    def test_runs_when_the_window_runs_out(self, db_conn, factory, run_period):
        league, _ = _league(db_conn, factory)
        ready_check.advance_if_due(db_conn, league.id)
        _expire_window(db_conn, league)
        assert ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_called_once()

    def test_away_gm_doesnt_hold_the_league_up(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory)
        ready_check.set_away(db_conn, b.id, True)
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)

    def test_everyone_away_waits_for_the_clock(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory)
        ready_check.set_away(db_conn, a.id, True)
        ready_check.set_away(db_conn, b.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)
        _expire_window(db_conn, league)
        assert ready_check.advance_if_due(db_conn, league.id)


class TestConfirmedPace:
    def test_no_clock(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory, pace="confirmed")
        assert not ready_check.advance_if_due(db_conn, league.id)
        assert _period(db_conn, league)["period_deadline"] is None
        assert ready_check.status(db_conn, league.id, a.id)["seconds_left"] is None

    def test_runs_only_when_everyone_is_ready(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory, pace="confirmed")
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)
        ready_check.set_ready(db_conn, league.id, b.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)


class TestWhenNothingRuns:
    def test_scheduled_pace_isnt_built(self, db_conn, factory, run_period):
        league, gms = _league(db_conn, factory, pace="scheduled")
        for gm in gms:
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)

    def test_lobby_has_nothing_to_ready_for(self, db_conn, factory, run_period):
        league, (a, _) = _league(db_conn, factory, state="lobby")
        with pytest.raises(ValueError):
            ready_check.set_ready(db_conn, league.id, a.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)

    def test_single_player_has_no_ready_check(self, db_conn, factory, run_period):
        league, (a,) = _league(db_conn, factory, humans=1)
        with pytest.raises(ValueError):
            ready_check.set_ready(db_conn, league.id, a.id, True)
        assert ready_check.status(db_conn, league.id, a.id) == {"multiplayer": False}

    def test_unready_takes_it_back(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory)
        ready_check.set_ready(db_conn, league.id, a.id, True)
        ready_check.set_ready(db_conn, league.id, a.id, False)
        ready_check.set_ready(db_conn, league.id, b.id, True)
        assert not ready_check.advance_if_due(db_conn, league.id)

    def test_another_request_already_running_it(
        self, db_conn, factory, run_period, request
    ):
        league, gms = _league(db_conn, factory)
        for gm in gms:
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
        with psycopg.connect(url, row_factory=dict_row) as other:
            with league_lock(other, league.id):
                assert not ready_check.advance_if_due(db_conn, league.id)
                assert ready_check.status(db_conn, league.id, gms[0].id)["simming"]
        run_period.assert_not_called()


def test_next_window_starts_when_the_period_ends(db_conn, factory, run_period):
    league, (a, b) = _league(db_conn, factory, window=60)
    for gm in (a, b):
        ready_check.set_ready(db_conn, league.id, gm.id, True)
    ready_check.advance_if_due(db_conn, league.id)
    assert 55 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 60
