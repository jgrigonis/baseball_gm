# src/db/repositories/sim_job_repo.py

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

# A running job whose worker hasn't checked in for this long is taken to have
# died with it (the worker checks in every few seconds; see src/worker.py).
STALE_SECONDS = 60

# Finished jobs are kept this long, so a page that asked for one can still
# read its result, then deleted.
KEEP_FINISHED_HOURS = 24


class SimJobRepository:
    """The queue of work that moves a league on (src/api/services/sim_jobs.py)."""

    def __init__(self, conn):
        self.conn = conn

    def add(
        self, league_id: str, kind: str, params: dict, gm_id: str | None
    ) -> str | None:
        """Queue a job. Returns its id, or None if the league already has one
        queued or running."""
        row = self.conn.execute(
            """INSERT INTO sim_jobs (id, league_id, kind, params, gm_id)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (league_id) WHERE state IN ('queued', 'running')
               DO NOTHING
               RETURNING id""",
            (str(uuid.uuid4()), league_id, kind, Jsonb(params), gm_id),
        ).fetchone()
        return row["id"] if row else None

    def get(self, job_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT *, EXTRACT(EPOCH FROM NOW() - created_at) AS age_seconds
               FROM sim_jobs WHERE id = %s""",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def active(self, league_id: str) -> dict | None:
        """The league's queued or running job, if it has one."""
        row = self.conn.execute(
            "SELECT * FROM sim_jobs WHERE league_id = %s"
            " AND state IN ('queued', 'running')",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def claim_next(self) -> dict | None:
        """Mark the oldest job that's ready to run as running and return it.
        Two workers never get the same job."""
        row = self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'running', started_at = NOW(), heartbeat_at = NOW()
               WHERE id = (
                   SELECT id FROM sim_jobs
                   WHERE state = 'queued' AND run_after <= NOW()
                   ORDER BY created_at
                   LIMIT 1
                   FOR UPDATE SKIP LOCKED
               )
               RETURNING *"""
        ).fetchone()
        return dict(row) if row else None

    def mark_running(self, job_id: str) -> None:
        self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'running', started_at = NOW(), heartbeat_at = NOW()
               WHERE id = %s""",
            (job_id,),
        )

    def heartbeat(self, job_id: str) -> None:
        self.conn.execute(
            "UPDATE sim_jobs SET heartbeat_at = NOW() WHERE id = %s", (job_id,)
        )

    def finish(self, job_id: str, result: dict) -> None:
        self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'done', result = %s, finished_at = NOW()
               WHERE id = %s""",
            (Jsonb(result), job_id),
        )

    def fail(self, job_id: str, error: str) -> None:
        self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'failed', error = %s, finished_at = NOW()
               WHERE id = %s""",
            (error, job_id),
        )

    def retry_later(self, job_id: str, seconds: float) -> None:
        """Put a job back in the queue, e.g. when the league was locked by a
        request (a trade, an admin change) at the moment it was picked up."""
        self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'queued', attempts = attempts + 1,
                   run_after = NOW() + make_interval(secs => %s),
                   started_at = NULL, heartbeat_at = NULL
               WHERE id = %s""",
            (seconds, job_id),
        )

    def fail_stale(self) -> list[str]:
        """Fail running jobs whose worker stopped checking in. Returns their
        ids."""
        rows = self.conn.execute(
            """UPDATE sim_jobs
               SET state = 'failed', finished_at = NOW(),
                   error = 'The sim stopped before it finished. Try again.'
               WHERE state = 'running'
                 AND heartbeat_at < NOW() - make_interval(secs => %s)
               RETURNING id""",
            (STALE_SECONDS,),
        ).fetchall()
        return [r["id"] for r in rows]

    def prune(self) -> int:
        """Delete finished jobs nobody will ask about any more."""
        return self.conn.execute(
            """DELETE FROM sim_jobs
               WHERE state IN ('done', 'failed')
                 AND finished_at < NOW() - make_interval(hours => %s)""",
            (KEEP_FINISHED_HOURS,),
        ).rowcount
