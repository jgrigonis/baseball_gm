# src/db/init.py

from .schema import SCHEMA_SQL
from src.db.migrations import run_migrations


def init_db(conn):
    """
    Ensure the database schema exists.
    Safe to call multiple times.
    """
    conn.executescript(SCHEMA_SQL)
    run_migrations(conn)
    conn.commit()
