# tests/api/test_ready_check.py
"""A multiplayer league sims its next period when every GM who isn't away is
ready, or, under timer pace, when the Decision Window runs out."""

import json
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
from src.db.repositories.sim_job_repo import SimJobRepository


@pytest.fixture
def run_period():
    """Stands in for the sim itself; these tests are about when it runs."""
    with patch.object(ready_check, "_run_period") as run:
        run.return_value = False  # didn't stop at the trade deadline
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
        """The period is queued, but the job can't run while something else
        holds the league (the worker would try again)."""
        league, gms = _league(db_conn, factory)
        for gm in gms:
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
        with psycopg.connect(url, row_factory=dict_row) as other:
            with league_lock(other, league.id):
                ready_check.advance_if_due(db_conn, league.id)
        # (The real worker leaves the job queued to try again, which shows as
        # simming: test_already_queued.)
        run_period.assert_not_called()

    def test_league_lock_alone_isnt_simming(self, db_conn, factory, request):
        """A trade, a budget save or another GM's poll holds the league lock
        for a moment; only a queued or running sim counts as simming."""
        league, gms = _league(db_conn, factory)
        url = request.config.getoption("--db-url") or os.environ["DATABASE_TEST_URL"]
        with psycopg.connect(url, row_factory=dict_row) as other:
            with league_lock(other, league.id):
                assert not ready_check.status(db_conn, league.id, gms[0].id)["simming"]

    def test_already_queued(self, db_conn, factory, run_period):
        """However many polls see the period come due, it's queued once."""
        league, gms = _league(db_conn, factory)
        for gm in gms:
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        SimJobRepository(db_conn).add(league.id, "period", {"sim_period": 0}, None)

        assert not ready_check.advance_if_due(db_conn, league.id)
        assert ready_check.status(db_conn, league.id, gms[0].id)["simming"]
        run_period.assert_not_called()


def test_next_window_starts_when_the_period_ends(db_conn, factory, run_period):
    league, (a, b) = _league(db_conn, factory, window=60)
    for gm in (a, b):
        ready_check.set_ready(db_conn, league.id, gm.id, True)
    ready_check.advance_if_due(db_conn, league.id)
    assert 55 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 60


def test_the_window_after_the_trade_deadline_is_three_times_as_long(
    db_conn, factory, run_period
):
    league, (a, b) = _league(db_conn, factory, window=60)
    run_period.return_value = True  # the sim stopped at the trade deadline
    for gm in (a, b):
        ready_check.set_ready(db_conn, league.id, gm.id, True)
    ready_check.advance_if_due(db_conn, league.id)
    assert 175 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 180


def _moves_to(state):
    """A stand-in period that moves the league to `state`."""

    def run(conn, league_id, *_):
        conn.execute("UPDATE leagues SET state = %s WHERE id = %s", (state, league_id))
        return False  # didn't stop at the trade deadline

    return run


class TestWhichWindow:
    """The draft gets the Draft Window and the preseason period, when GMs set
    their first lineup, gets the Lineup Window, as does the offseason (or the
    Decision Window, if that's longer)."""

    def _set_windows(self, db, league):
        db.execute(
            """UPDATE leagues SET decision_window_sec = 60, draft_window_sec = 900,
                   lineup_window_sec = 1800 WHERE id = %s""",
            (league.id,),
        )

    def test_draft_opens_the_draft_window(self, db_conn, factory, run_period):
        league, (a, _) = _league(db_conn, factory, state="draft")
        self._set_windows(db_conn, league)
        ready_check.advance_if_due(db_conn, league.id)
        assert (
            895 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 900
        )

    def test_after_the_draft_comes_the_lineup_window(
        self, db_conn, factory, run_period
    ):
        league, (a, b) = _league(db_conn, factory, state="draft")
        self._set_windows(db_conn, league)
        run_period.side_effect = _moves_to("preseason")
        for gm in (a, b):
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert (
            1795 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 1800
        )

    def test_season_uses_the_decision_window(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory, state="preseason")
        self._set_windows(db_conn, league)
        run_period.side_effect = _moves_to("season")
        for gm in (a, b):
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert 55 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 60

    def test_offseason_gets_the_lineup_window(self, db_conn, factory, run_period):
        # Expiring deals and re-signs take longer than one decision.
        league, (a, b) = _league(db_conn, factory, state="playoffs")
        self._set_windows(db_conn, league)
        run_period.side_effect = _moves_to("offseason")
        for gm in (a, b):
            ready_check.set_ready(db_conn, league.id, gm.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        assert (
            1795 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 1800
        )

    def test_offseason_keeps_a_longer_decision_window(
        self, db_conn, factory, run_period
    ):
        league, (a, _) = _league(db_conn, factory, state="offseason")
        db_conn.execute(
            """UPDATE leagues SET decision_window_sec = 500,
                   lineup_window_sec = 120 WHERE id = %s""",
            (league.id,),
        )
        ready_check.advance_if_due(db_conn, league.id)
        assert 495 <= ready_check.status(db_conn, league.id, a.id)["seconds_left"] <= 500


class TestPlayoffs:
    """In the playoffs a GM whose team didn't make it, or is knocked out,
    counts as away; with nobody left, the playoffs sim straight through."""

    def _team_of(self, db, gm):
        return db.execute("SELECT team_id FROM gms WHERE id = %s", (gm.id,)).fetchone()[
            "team_id"
        ]

    def _bracket(self, db, factory, league, series):
        """series: (name, high_team_id, low_team_id, high_wins, low_wins)."""
        season = factory.season()
        factory.league_season(league, season)
        for name, high, low, high_wins, low_wins in series:
            sid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
                (sid, season.id, name),
            )
            results = [high] * high_wins + [low] * low_wins + [None]
            for i, winner in enumerate(results):
                db.execute(
                    """INSERT INTO games (id, game_date, season_id, series_id,
                           home_team_id, away_team_id, completed, winner_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        str(uuid.uuid4()),
                        f"2025-10-{i + 1:02d}",
                        season.id,
                        sid,
                        high,
                        low,
                        1 if winner else 0,
                        winner,
                    ),
                )

    def _playoff_league(self, db, factory):
        league, (a, b) = _league(db, factory, state="playoffs")
        return league, a, b, self._team_of(db, a), self._team_of(db, b)

    def test_gm_who_missed_the_playoffs_is_away(self, db_conn, factory, run_period):
        league, a, b, team_a, _ = self._playoff_league(db_conn, factory)
        self._bracket(
            db_conn, factory, league, [("1v8", team_a, factory.team().id, 0, 0)]
        )
        status = ready_check.status(db_conn, league.id, b.id)
        assert status["you_out"] and not status["you_away"]
        assert status["waiting_on"] == ["GM 0"]
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_called_once()

    def test_eliminated_gm_is_away(self, db_conn, factory, run_period):
        league, a, b, team_a, team_b = self._playoff_league(db_conn, factory)
        self._bracket(
            db_conn,
            factory,
            league,
            [
                ("1v8", team_a, factory.team().id, 1, 0),
                ("2v7", factory.team().id, team_b, 3, 1),
            ],
        )
        assert ready_check.status(db_conn, league.id, a.id)["waiting_on"] == ["GM 0"]
        assert ready_check.status(db_conn, league.id, b.id)["you_out"]
        assert not ready_check.advance_if_due(db_conn, league.id)
        ready_check.set_ready(db_conn, league.id, a.id, True)
        assert ready_check.advance_if_due(db_conn, league.id)

    def test_no_gm_in_the_playoffs_sims_straight_through(
        self, db_conn, factory, run_period
    ):
        league, a, b, _, _ = self._playoff_league(db_conn, factory)
        self._bracket(
            db_conn,
            factory,
            league,
            [("1v8", factory.team().id, factory.team().id, 0, 0)],
        )
        days = []

        def play_day(conn, league_id, *_):
            days.append(1)
            if len(days) == 5:
                conn.execute(
                    "UPDATE leagues SET state = 'offseason' WHERE id = %s", (league_id,)
                )

        run_period.side_effect = play_day
        # No one ready and the window still open, yet it runs to the end.
        assert ready_check.advance_if_due(db_conn, league.id)
        assert run_period.call_count == 5
        assert (
            ready_check.status(db_conn, league.id, a.id)["league_state"] == "offseason"
        )

    def test_everyone_away_sims_straight_through(self, db_conn, factory, run_period):
        league, a, b, team_a, team_b = self._playoff_league(db_conn, factory)
        self._bracket(db_conn, factory, league, [("1v8", team_a, team_b, 0, 0)])
        ready_check.set_away(db_conn, a.id, True)
        ready_check.set_away(db_conn, b.id, True)
        run_period.side_effect = lambda conn, league_id, *_: conn.execute(
            "UPDATE leagues SET state = 'offseason' WHERE id = %s", (league_id,)
        )
        assert ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_called_once()

    def test_stops_once_a_gm_is_back(self, db_conn, factory, run_period):
        league, a, b, team_a, _ = self._playoff_league(db_conn, factory)
        self._bracket(
            db_conn, factory, league, [("1v8", team_a, factory.team().id, 0, 0)]
        )
        ready_check.set_away(db_conn, a.id, True)
        run_period.side_effect = lambda conn, *_: conn.execute(
            "UPDATE gms SET is_away = FALSE WHERE id = %s", (a.id,)
        )
        assert ready_check.advance_if_due(db_conn, league.id)
        run_period.assert_called_once()
        assert ready_check.status(db_conn, league.id, a.id)["waiting_on"] == ["GM 0"]

    def test_outside_the_playoffs_nobody_is_out(self, db_conn, factory, run_period):
        league, (a, b) = _league(db_conn, factory, state="season")
        status = ready_check.status(db_conn, league.id, a.id)
        assert not status["you_out"]
        assert sorted(status["waiting_on"]) == ["GM 0", "GM 1"]


class TestTopBarDate:
    """The status poll brings the date, so the top bar moves on after a
    period without a reload."""

    def test_status_poll_has_the_next_game_date(self, db_conn, factory, run_period):
        from src.api.routers.ready import _status

        league, (a, _) = _league(db_conn, factory)
        season = factory.season()
        factory.league_season(league, season)
        for day in ("2025-04-01", "2025-04-02"):
            factory.game_with_teams(season=season, game_date=day)
        db_conn.execute(
            "UPDATE games SET completed = 0 WHERE season_id = %s", (season.id,)
        )

        def date():
            return json.loads(_status(db_conn, league.id, {"id": a.id}).body)[
                "current_date"
            ]

        assert str(date()) == "2025-04-01"
        db_conn.execute(
            "UPDATE games SET completed = 1 WHERE season_id = %s AND game_date = '2025-04-01'",
            (season.id,),
        )
        assert str(date()) == "2025-04-02"


def test_preseason_period_with_open_bids_settles_without_games(monkeypatch):
    """Bids stay open into a multiplayer preseason; its first period settles
    them, with no games, and the next one plays Opening Day (Josh,
    2026-11-12)."""
    calls = []
    monkeypatch.setattr(ready_check.offseason_fa, "bidding_open", lambda c, l: True)
    monkeypatch.setattr(
        ready_check.offseason_fa, "close_bidding", lambda c, l: calls.append("close")
    )
    monkeypatch.setattr(ready_check, "sim_days", lambda *a: calls.append("sim") or {})
    assert ready_check._run_period(None, "L", "preseason", 3) is False
    assert calls == ["close"]
    monkeypatch.setattr(ready_check.offseason_fa, "bidding_open", lambda c, l: False)
    ready_check._run_period(None, "L", "preseason", 3)
    assert calls == ["close", "sim"]
