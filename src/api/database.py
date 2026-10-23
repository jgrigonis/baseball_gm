# src/api/database.py
#
# Thin wrapper around psycopg3. Keeps the same dict_row pattern the sim
# engine uses — no ORM, no magic. FastAPI gets a get_db() dependency that
# yields a connection and closes it when the request is done.

from __future__ import annotations

import psycopg
from collections.abc import Generator
from contextlib import contextmanager

from src.db.connection import get_connection


@contextmanager
def db_transaction() -> Generator[psycopg.Connection]:
    """Context manager: commits on exit, rolls back on exception."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── FastAPI dependency ────────────────────────────────────────────────────────


def get_db() -> Generator[psycopg.Connection]:
    """
    FastAPI dependency. Yields a connection inside db_transaction(): commits
    if the request succeeds, rolls back if it raises, and always closes.

    Usage:
        @router.get("/things")
        def list_things(db: psycopg.Connection = Depends(get_db)):
            ...
    """
    with db_transaction() as conn:
        yield conn
