# src/api/services/sim_jobs.py
#
# Work that moves a league on (simming days, the playoffs, the offseason, the
# draft, starting the league, a ready-check period) runs as a job: the web
# request queues it and answers at once with the job's id, and the sim worker
# (src/worker.py) runs it. The page then polls the job until it's done. So a
# sim that takes minutes never holds a web request open, or a web worker
# busy, and a server timeout can't cut it off halfway.
#
# A league has at most one job queued or running; asking for another while
# it does is LeagueBusy, the same as when two requests raced for the league
# lock. The worker still takes the league lock while it runs a job, since
# other requests (trades, admin changes, leaving the league) take it too.
#
# With SIM_WORKER=inline (the tests) there's no worker: queuing a job runs it
# straight away, inside the request.

from __future__ import annotations

import logging
from collections.abc import Callable

from src.api.services import career, coach
from src.api.services.draft_execute import execute_blitz_draft
from src.api.services.league_start import start_league
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_days
from src.api.services.sim_playoff import sim_playoff
from src.config import settings
from src.db.connection import rollback_quietly
from src.db.locks import LeagueBusy, league_lock
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.sim_job_repo import SimJobRepository

log = logging.getLogger(__name__)

# The Postgres channel the web server notifies when it queues a job, so an
# idle worker starts on it without waiting for its next look at the queue.
CHANNEL = "sim_jobs"

# When the league is locked as the worker picks a job up (a trade being
# accepted, an admin change), it tries again this often, this many times.
RETRY_SECONDS = 2
MAX_ATTEMPTS = 30


# ── What each kind of job does ────────────────────────────────────────────────
#
# Each runs with the league lock held and returns the job's result, which the
# page reads when it polls (src/api/routers/sim.py adds what's per-GM, like
# injury news, at that point). Rule errors are ValueErrors, shown to the GM.


def _sim(conn, league_id: str, params: dict) -> dict:
    summary = sim_days(league_id, conn, params["count"])
    coach.mark(conn, league_id, "play")
    return summary


def _playoffs(conn, league_id: str, params: dict) -> dict:
    return sim_playoff(league_id, conn, mode=params.get("mode", "game"))


def _offseason(conn, league_id: str, params: dict) -> dict:
    return {"ok": True, **run_offseason(league_id, conn)}


def _draft(conn, league_id: str, params: dict) -> dict:
    draft = DraftRepository(conn).get_current_for_league(league_id)
    if not draft:
        return {"redirect": f"/leagues/{league_id}/draft"}
    if draft["state"] != "complete":
        execute_blitz_draft(draft["id"], conn)
    return {"redirect": f"/leagues/{league_id}/draft/results"}


def _start(conn, league_id: str, params: dict) -> dict:
    start_league(league_id, conn)
    return {"redirect": f"/leagues/{league_id}/"}


def _period(conn, league_id: str, params: dict) -> dict:
    from src.api.services import ready_check

    return {"ran": ready_check.run_period(conn, league_id, params["sim_period"])}


KINDS: dict[str, Callable[[object, str, dict], dict]] = {
    "sim": _sim,
    "playoffs": _playoffs,
    "offseason": _offseason,
    "draft": _draft,
    "start": _start,
    "period": _period,
}


# ── Queuing ───────────────────────────────────────────────────────────────────


def submit(
    conn, league_id: str, kind: str, params: dict | None = None, gm_id=None
) -> str:
    """Queue a job and return its id. Raises LeagueBusy if the league already
    has one queued or running. Commits, so the worker can see it."""
    if kind not in KINDS:
        raise ValueError(f"Unknown job '{kind}'.")
    repo = SimJobRepository(conn)
    job_id = repo.add(league_id, kind, params or {}, gm_id)
    if job_id is None:
        raise LeagueBusy(league_id)
    conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, job_id))
    conn.commit()
    if settings.sim_worker == "inline":
        repo.mark_running(job_id)
        run(conn, repo.get(job_id), repo)
    return job_id


def league_has_job(conn, league_id: str) -> bool:
    return SimJobRepository(conn).active(league_id) is not None


# ── Running ───────────────────────────────────────────────────────────────────


def _record_careers(conn, league_id: str) -> None:
    """Bring each person's career record up to date with what the job
    played (services/career.py). In a savepoint, so a problem there is
    logged and never undoes the sim itself."""
    try:
        with conn.transaction():
            career.record_league(conn, league_id)
    except Exception:
        log.exception("League %s: couldn't update career records", league_id)


def run(conn, job: dict, jobs: SimJobRepository) -> str:
    """
    Run a claimed job on ``conn`` and record how it went with ``jobs``, which
    the worker keeps on a separate connection so its bookkeeping never mixes
    with the sim's transaction. Returns the job's new state: 'done',
    'failed', or 'queued' when the league was locked and it will try again.
    """
    league_id = job["league_id"]
    runner = KINDS.get(job["kind"])
    try:
        if runner is None:
            raise ValueError(f"Unknown job '{job['kind']}'.")
        with league_lock(conn, league_id):
            result = runner(conn, league_id, job["params"] or {})
            _record_careers(conn, league_id)
            conn.commit()
    except LeagueBusy as e:
        rollback_quietly(conn)
        if settings.sim_worker != "inline" and job["attempts"] < MAX_ATTEMPTS:
            jobs.retry_later(job["id"], RETRY_SECONDS)
            state = "queued"
        else:
            jobs.fail(job["id"], str(e))
            state = "failed"
    except ValueError as e:
        rollback_quietly(conn)
        log.info("League %s: %s job rejected: %s", league_id, job["kind"], e)
        jobs.fail(job["id"], str(e))
        state = "failed"
    except Exception:
        rollback_quietly(conn)
        log.exception("League %s: %s job %s failed", league_id, job["kind"], job["id"])
        jobs.fail(job["id"], "Something went wrong.")
        state = "failed"
    else:
        jobs.finish(job["id"], result)
        state = "done"
    if jobs.conn is conn:
        conn.commit()
    return state
