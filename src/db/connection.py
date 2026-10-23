# src/db/connection.py
import logging
import os

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)


def get_connection(url: str | None = None) -> psycopg.Connection:
    """
    Return a psycopg3 connection.

    Connection URL is read from DATABASE_URL environment variable.
    The `db` parameter is accepted for backwards compatibility but ignored —
    all configuration is done via DATABASE_URL.

    dict_row factory means rows support both row["column"] and row.get("column"),
    matching the old sqlite3.Row behaviour everywhere in the codebase.
    """
    if url is None:
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Example: postgresql://user@localhost/baseball_manager"
        )
    conn = psycopg.connect(url, row_factory=dict_row)
    return conn


def rollback_quietly(conn: psycopg.Connection) -> None:
    """
    Roll back ``conn`` while already handling another error.

    A rollback that fails (e.g. the connection dropped) is logged rather than
    raised, so it never hides the error that caused the rollback.
    """
    try:
        conn.rollback()
    except psycopg.Error:
        log.warning("Rollback failed", exc_info=True)
