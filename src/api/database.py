# src/api/database.py
#
# Thin wrapper around sqlite3. Keeps the same sqlite3.Row pattern the sim
# engine uses — no ORM, no magic. FastAPI gets a get_db() dependency that
# yields a connection and closes it when the request is done.

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from src.config import settings
from src.db.connection import get_connection

# def get_connection() -> sqlite3.Connection:
#     """Open a new connection with WAL mode and Row factory. Caller must close."""
#     conn = sqlite3.connect(_db_path())
#     conn.row_factory = sqlite3.Row
#     conn.execute("PRAGMA foreign_keys = ON")
#     conn.execute("PRAGMA journal_mode = WAL")
#     return conn


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
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


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency. Yields a connection; commits and closes after the
    request regardless of outcome.

    Usage:
        @router.get("/things")
        def list_things(db: sqlite3.Connection = Depends(get_db)):
            ...
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
