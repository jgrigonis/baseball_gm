# src/worker.py
#
# The sim worker: runs the jobs the web server queues (simming days, the
# playoffs, the offseason, the draft, starting a league, ready-check periods;
# see src/api/services/sim_jobs.py). Run it alongside the web server, from
# the repo root:
#
#   uv run python -m src.worker
#
# Each worker runs one job at a time. Run more of them for more leagues at
# once: they share the queue in Postgres and never pick up the same job, and
# a league never has more than one job, so they never sim the same league.
#
# SIGTERM (e.g. `docker stop`) lets the job in hand finish, then exits; give
# it long enough to (a full season can take minutes). Ctrl-C stops at once.
# A job cut off partway fails with a message asking the GM to try again;
# every sim commits as it goes, so what had been played stays played.

from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from src.api.services import sim_jobs, turn_alerts
from src.db.connection import get_connection, rollback_quietly
from src.db.repositories.sim_job_repo import SimJobRepository
from src.util.logger import configure_app_logging

log = logging.getLogger("src.worker")

# How long to wait for a notification of a new job before looking at the
# queue anyway (a job retried later doesn't notify).
IDLE_SECONDS = 2

# How often the worker tells Postgres the job it's running is still alive.
# Must be well under sim_job_repo.STALE_SECONDS.
HEARTBEAT_SECONDS = 10

# How often to fail jobs whose worker died and delete old finished ones.
HOUSEKEEPING_SECONDS = 60

# How often to move on multiplayer leagues whose window has run out, with
# nobody's page open to notice (src/api/services/turn_alerts.py).
CLOCK_SECONDS = 5

CUT_OFF = "The sim stopped before it finished. Try again."


class _Heartbeat:
    """Keep a running job's heartbeat_at fresh from a background thread, on
    its own connection, while the main thread sims."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.done.set()
        self.thread.join()

    def _beat(self) -> None:
        conn = get_connection()
        conn.autocommit = True
        try:
            while not self.done.wait(HEARTBEAT_SECONDS):
                SimJobRepository(conn).heartbeat(self.job_id)
        except Exception:
            log.warning("Heartbeat for job %s failed", self.job_id, exc_info=True)
        finally:
            conn.close()


class Worker:
    def __init__(self):
        self.stopping = threading.Event()
        self.jobs_conn = get_connection()
        self.jobs_conn.autocommit = True
        self.jobs = SimJobRepository(self.jobs_conn)
        self.jobs_conn.execute(f"LISTEN {sim_jobs.CHANNEL}")
        self.sim_conn = get_connection()
        self.last_housekeeping = 0.0
        self.last_clock = 0.0

    def run_forever(self) -> None:
        log.info("Sim worker started.")
        while not self.stopping.is_set():
            self._housekeeping()
            self._clock()
            job = self.jobs.claim_next()
            if job:
                self.run_one(job)
            else:
                self._wait_for_job()
        log.info("Sim worker stopped.")

    def run_one(self, job: dict) -> None:
        log.info("League %s: %s job %s", job["league_id"], job["kind"], job["id"])
        started = time.monotonic()
        try:
            with _Heartbeat(job["id"]):
                state = sim_jobs.run(self.sim_conn, job, self.jobs)
        except BaseException:
            # Ctrl-C, or the sim connection died under the job.
            self.jobs.fail(job["id"], CUT_OFF)
            raise
        finally:
            if self.sim_conn.closed or self.sim_conn.broken:
                self.sim_conn = get_connection()
        log.info(
            "League %s: %s job %s %s in %.1fs",
            job["league_id"],
            job["kind"],
            job["id"],
            state,
            time.monotonic() - started,
        )

    def _wait_for_job(self) -> None:
        # Returns on the first notification, or after IDLE_SECONDS.
        for _ in self.jobs_conn.notifies(timeout=IDLE_SECONDS, stop_after=1):
            pass

    def _housekeeping(self) -> None:
        if time.monotonic() - self.last_housekeeping < HOUSEKEEPING_SECONDS:
            return
        self.last_housekeeping = time.monotonic()
        for job_id in self.jobs.fail_stale():
            log.warning("Job %s: its worker stopped; marked failed", job_id)
        self.jobs.prune()

    def _clock(self) -> None:
        if time.monotonic() - self.last_clock < CLOCK_SECONDS:
            return
        self.last_clock = time.monotonic()
        try:
            queued = turn_alerts.advance_due_leagues(self.sim_conn)
        except Exception:
            log.exception("The league clock failed")
            rollback_quietly(self.sim_conn)
            return
        if queued:
            log.info("League clock: queued %d period(s)", queued)

    def close(self) -> None:
        self.sim_conn.close()
        self.jobs_conn.close()


def main() -> int:
    configure_app_logging(fmt="%(levelname)s %(name)s: %(message)s")
    worker = Worker()

    def stop(signum, frame):
        log.info("Stopping once the current job is done…")
        worker.stopping.set()

    signal.signal(signal.SIGTERM, stop)
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
