"""
sim_jobs: the queue of work that moves a league on (simming days, the
playoffs, the offseason, the draft, starting the league, a ready-check
period). The web server adds a job and the sim worker (src/worker.py) runs
it, so no web request waits on a sim. At most one job per league is queued
or running at a time.
"""

VERSION = 29


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sim_jobs (
            id              TEXT PRIMARY KEY,
            league_id       TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            kind            TEXT NOT NULL,
            params          JSONB NOT NULL DEFAULT '{}',
            gm_id           TEXT,
            state           TEXT NOT NULL DEFAULT 'queued'
                                CHECK (state IN ('queued', 'running', 'done', 'failed')),
            result          JSONB,
            error           TEXT,
            attempts        INTEGER NOT NULL DEFAULT 0,
            run_after       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at      TIMESTAMPTZ,
            heartbeat_at    TIMESTAMPTZ,
            finished_at     TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sim_jobs_one_active"
        " ON sim_jobs(league_id) WHERE state IN ('queued', 'running')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sim_jobs_queue"
        " ON sim_jobs(run_after) WHERE state = 'queued'"
    )
