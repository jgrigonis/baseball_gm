# src/db/locks.py
#
# One lock per league around anything that advances it (simming days or
# playoff games, the offseason, the draft, starting the league), so two
# requests can't play the same games twice.
#
# This is a Postgres advisory lock: a named flag Postgres holds for us, not a
# lock on any row. It belongs to the connection rather than the transaction,
# so it stays held through the commit after every game, and Postgres drops it
# if the connection closes. Because Postgres holds it, it works across any
# number of server processes.
#
# A row lock (SELECT ... FOR UPDATE on the league) would not work here: it is
# released at the first commit, and the sim commits after each game.

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from psycopg.pq import TransactionStatus

from src.db.connection import rollback_quietly


class LeagueBusy(Exception):
    """Another request already holds this league's lock."""

    def __init__(self, league_id: str):
        super().__init__("A sim is already running for this league.")
        self.league_id = league_id


def _key(league_id: str) -> str:
    return f"league:{league_id}"


@contextmanager
def league_lock(conn, league_id: str) -> Generator[None]:
    """
    Hold the league's lock for the duration of the block.

    Doesn't wait: raises LeagueBusy at once if another request holds it,
    rather than queueing behind a sim that may take minutes.
    """
    got = conn.execute(
        "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS got",
        (_key(league_id),),
    ).fetchone()["got"]
    if not got:
        raise LeagueBusy(league_id)
    try:
        yield
    finally:
        # A dropped connection has already released it.
        if not conn.closed:
            # A failed statement leaves the transaction aborted, and the
            # unlock can't run until it is rolled back. The request is
            # failing anyway.
            if conn.info.transaction_status == TransactionStatus.INERROR:
                rollback_quietly(conn)
            conn.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (_key(league_id),),
            )
