# src/db/init.py

from src.db.schema import SCHEMA_SQL
from src.db.migrations import run_migrations


def _split_statements(sql: str) -> list[str]:
    """
    Split a SQL string into individual statements, stripping comments and
    empty lines. Safe for both DDL and DML.
    """
    statements = []
    current: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        # Skip single-line comments and blank lines
        if stripped.startswith("--") or not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    return statements


def init_db(conn) -> None:
    """
    Ensure the database schema exists.
    Safe to call multiple times (idempotent — uses IF NOT EXISTS throughout).
    """
    try:
        for stmt in _split_statements(SCHEMA_SQL):
            # print(stmt)
            # print("*"*80)
            conn.execute(stmt)
        # print("finished statements")
        run_migrations(conn)
        conn.commit()
        # print("finished migration")

    except Exception:
        conn.rollback()
        raise


def verify_schema(conn) -> bool:
    """
    Verify that the database schema is properly initialized.

    Returns:
        True if schema is valid.

    Raises:
        RuntimeError: If critical tables are missing.
    """
    cursor = conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = {row["table_name"] for row in cursor.fetchall()}

    required_tables = {
        "schema_migrations",
        "players",
        "player_skills",
        "teams",
        "leagues",
        "seasons",
        "games",
    }

    missing = required_tables - tables
    if missing:
        raise RuntimeError(f"Missing required tables: {missing}")

    return True
