# src/db/connection.py
import sqlite3
from pathlib import Path
from src.util.locations import LEAGUE_FILES_DIR


def get_connection(db_name: str = "league.db") -> sqlite3.Connection:
    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / db_name)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
