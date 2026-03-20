# src/db/connection.py
import sqlite3
from pathlib import Path
from src.util.locations import LEAGUE_FILES_DIR


def get_connection(db: str | Path = "league.db") -> sqlite3.Connection:
    p = Path(db)
    path = Path(LEAGUE_FILES_DIR) / p if p.parent == Path(".") else p
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
