# tests/api/test_sim_jobs.py
"""Sims run as queued jobs (src/api/services/sim_jobs.py): one per league at a
time, rule errors shown to the GM, and the page polls for the result. The
tests run with SIM_WORKER=inline, so a queued job runs straight away."""

import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm
from src.api.main import app
from src.api.services import sim_jobs
from src.db.locks import LeagueBusy
from src.db.repositories.sim_job_repo import SimJobRepository


@pytest.fixture(autouse=True)
def empty_queue(db_conn):
    """Other tests can commit jobs (production code commits as it goes);
    the queue tests here need it to start empty."""
    db_conn.execute("DELETE FROM sim_jobs")


@pytest.fixture
def runner():
    """Stands in for what a job does; these tests are about the queue."""
    with patch.dict(sim_jobs.KINDS, {"sim": lambda conn, lid, p, report: {"ran": p}}):
        yield


@pytest.fixture
def league(factory):
    return factory.league(state="season")


def _job(db, job_id):
    return SimJobRepository(db).get(job_id)


class TestSubmit:
    def test_runs_the_job_and_keeps_its_result(self, db_conn, league, runner):
        job_id = sim_jobs.submit(db_conn, league.id, "sim", {"count": 3}, "gm-1")

        job = _job(db_conn, job_id)
        assert job["state"] == "done"
        assert job["result"] == {"ran": {"count": 3}}
        assert job["gm_id"] == "gm-1"

    def test_one_job_per_league(self, db_conn, league, runner):
        SimJobRepository(db_conn).add(league.id, "sim", {}, None)

        with pytest.raises(LeagueBusy):
            sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})

    def test_another_once_the_first_is_done(self, db_conn, league, runner):
        sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})
        job_id = sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})

        assert _job(db_conn, job_id)["state"] == "done"

    def test_unknown_kind(self, db_conn, league):
        with pytest.raises(ValueError):
            sim_jobs.submit(db_conn, league.id, "teleport")


class TestFailures:
    def test_rule_error_is_shown(self, db_conn, league):
        def broken(conn, league_id, params, report):
            raise ValueError("League is in state 'draft' — cannot sim.")

        with patch.dict(sim_jobs.KINDS, {"sim": broken}):
            job_id = sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})

        job = _job(db_conn, job_id)
        assert job["state"] == "failed"
        assert job["error"] == "League is in state 'draft' — cannot sim."

    def test_unexpected_error_is_hidden_and_logged(self, db_conn, league, caplog):
        secret = "/home/someone/src/secret_module.py"

        def broken(conn, league_id, params, report):
            raise RuntimeError(secret)

        with patch.dict(sim_jobs.KINDS, {"sim": broken}):
            with caplog.at_level(logging.ERROR):
                job_id = sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})

        job = _job(db_conn, job_id)
        assert job["state"] == "failed"
        assert job["error"] == "Something went wrong."
        (record,) = [r for r in caplog.records if r.exc_info]
        assert secret in str(record.exc_info[1])

    def test_failed_work_is_rolled_back(self, db_conn, league):
        def broken(conn, league_id, params, report):
            conn.execute(
                "UPDATE leagues SET name = 'Half done' WHERE id = %s", (league_id,)
            )
            raise RuntimeError

        with patch.dict(sim_jobs.KINDS, {"sim": broken}):
            sim_jobs.submit(db_conn, league.id, "sim", {"count": 1})

        name = db_conn.execute(
            "SELECT name FROM leagues WHERE id = %s", (league.id,)
        ).fetchone()["name"]
        assert name == "Test League"


class TestReport:
    def test_a_job_can_say_what_its_doing(self, db_conn, league):
        seen = []

        def work(conn, league_id, params, report):
            report("Halfway")
            seen.append(_job(conn, job_id)["stage"])
            return {}

        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "sim", {}, None)
        repo.mark_running(job_id)
        with patch.dict(sim_jobs.KINDS, {"sim": work}):
            sim_jobs.run(db_conn, repo.get(job_id), repo)

        assert seen == ["Halfway"]


class TestLockedLeague:
    """The league lock is held by a request (a trade, an admin change) when
    the worker picks the job up."""

    def _run_locked(self, db_conn, league, attempts):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "sim", {"count": 1}, None)
        db_conn.execute(
            "UPDATE sim_jobs SET attempts = %s WHERE id = %s", (attempts, job_id)
        )
        repo.mark_running(job_id)
        # As submit() would: the job outlives the sim's rollback.
        db_conn.commit()
        with (
            patch.object(sim_jobs.settings, "sim_worker", "separate"),
            patch.object(sim_jobs, "league_lock", side_effect=LeagueBusy(league.id)),
        ):
            state = sim_jobs.run(db_conn, repo.get(job_id), repo)
        return state, repo.get(job_id)

    def test_tries_again_later(self, db_conn, league):
        state, job = self._run_locked(db_conn, league, attempts=0)

        assert state == "queued"
        assert job["state"] == "queued"
        assert job["attempts"] == 1
        # Not straight away: run_after is in the future.
        assert SimJobRepository(db_conn).claim_next() is None

    def test_gives_up_eventually(self, db_conn, league):
        state, job = self._run_locked(db_conn, league, attempts=sim_jobs.MAX_ATTEMPTS)

        assert state == "failed"
        assert job["error"] == "A sim is already running for this league."


class TestQueue:
    def test_claims_the_oldest_ready_job_once(self, db_conn, factory):
        repo = SimJobRepository(db_conn)
        first = repo.add(factory.league().id, "sim", {}, None)
        second = repo.add(factory.league().id, "sim", {}, None)
        db_conn.execute(
            "UPDATE sim_jobs SET created_at = created_at - INTERVAL '1 minute'"
            " WHERE id = %s",
            (first,),
        )

        assert repo.claim_next()["id"] == first
        assert repo.claim_next()["id"] == second
        assert repo.claim_next() is None
        assert repo.get(first)["state"] == "running"

    def test_job_whose_worker_died_fails(self, db_conn, league):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "sim", {}, None)
        repo.mark_running(job_id)
        db_conn.execute(
            "UPDATE sim_jobs SET heartbeat_at = NOW() - INTERVAL '5 minutes'"
            " WHERE id = %s",
            (job_id,),
        )

        assert job_id in repo.fail_stale()
        assert repo.get(job_id)["state"] == "failed"
        # ...which frees the league for the next one.
        assert repo.add(league.id, "sim", {}, None)

    def test_live_job_is_left_alone(self, db_conn, league):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "sim", {}, None)
        repo.mark_running(job_id)

        assert job_id not in repo.fail_stale()

    def test_old_finished_jobs_are_deleted(self, db_conn, league):
        repo = SimJobRepository(db_conn)
        old = repo.add(league.id, "sim", {}, None)
        repo.finish(old, {})
        db_conn.execute(
            "UPDATE sim_jobs SET finished_at = NOW() - INTERVAL '2 days' WHERE id = %s",
            (old,),
        )
        recent = repo.add(league.id, "sim", {}, None)
        repo.finish(recent, {})

        repo.prune()

        assert repo.get(old) is None
        assert repo.get(recent) is not None


class TestPolling:
    @pytest.fixture
    def client(self, db_conn):
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_gm] = lambda: {"id": "gm-1"}
        yield TestClient(app)
        app.dependency_overrides.clear()

    def _poll(self, client, league, job_id):
        return client.get(f"/leagues/{league.id}/jobs/{job_id}").json()

    def test_queued(self, client, db_conn, league):
        job_id = SimJobRepository(db_conn).add(league.id, "sim", {}, None)

        assert self._poll(client, league, job_id) == {
            "state": "queued",
            "stage": None,
            "waiting_for_worker": False,
        }

    def test_running_says_what_its_doing(self, client, db_conn, league):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "start", {}, None)
        repo.mark_running(job_id)
        repo.set_stage(job_id, "Simulating league history…")

        body = self._poll(client, league, job_id)
        assert body["state"] == "running"
        assert body["stage"] == "Simulating league history…"

    def test_queued_a_while_says_the_worker_is_missing(self, client, db_conn, league):
        job_id = SimJobRepository(db_conn).add(league.id, "sim", {}, None)
        db_conn.execute(
            "UPDATE sim_jobs SET created_at = NOW() - INTERVAL '1 minute' WHERE id = %s",
            (job_id,),
        )

        assert self._poll(client, league, job_id)["waiting_for_worker"]

    def test_failed(self, client, db_conn, league):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "offseason", {}, None)
        repo.fail(job_id, "League must be in 'offseason' state")

        assert self._poll(client, league, job_id) == {
            "state": "failed",
            "detail": "League must be in 'offseason' state",
        }

    def test_done_sim_has_the_league_state_and_my_news(self, client, db_conn, league):
        repo = SimJobRepository(db_conn)
        job_id = repo.add(league.id, "sim", {}, None)
        repo.finish(job_id, {"games_played": 15})

        body = self._poll(client, league, job_id)

        assert body["state"] == "done"
        assert body["games_played"] == 15
        assert body["league_state"] == "season"
        assert "current_date" in body
        assert body["new_injuries"] == []

    def test_another_leagues_job_is_not_found(self, client, db_conn, factory, league):
        job_id = SimJobRepository(db_conn).add(factory.league().id, "sim", {}, None)

        r = client.get(f"/leagues/{league.id}/jobs/{job_id}")

        assert r.status_code == 404

    def test_sim_route_queues_a_job(self, client, db_conn, league, runner):
        from src.api.dependencies import (
            require_active_league,
            require_single_player,
            require_unpaused,
        )

        for dep in (require_active_league, require_single_player, require_unpaused):
            app.dependency_overrides[dep] = lambda: None

        r = client.post(f"/leagues/{league.id}/sim", json={"count": 2})

        assert r.status_code == 202
        job_id = r.json()["job_id"]
        assert r.json()["poll"] == f"/leagues/{league.id}/jobs/{job_id}"
        assert _job(db_conn, job_id)["params"] == {"count": 2}
