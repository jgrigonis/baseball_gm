# src/db/init.py

from .schema import SCHEMA_SQL


def init_db(conn):
    """
    Ensure the database schema exists.
    Safe to call multiple times.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
