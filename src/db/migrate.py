# src/db/migrate.py
#
# Brings the database schema up to date: creates any missing tables and runs
# pending migrations. Run it once before starting the web server and the sim
# worker, e.g. as a deploy step:
#
#   uv run python -m src.db.migrate
#
# The web server doesn't migrate on startup, since every one of its worker
# processes would try at once; it refuses to start while migrations are
# pending instead. Two copies of this command can run at the same time (say,
# two containers starting together): the second waits for the first, then
# finds nothing left to do.

from __future__ import annotations

import logging
import sys

from src.db.connection import get_connection
from src.db.init import init_db
from src.db.migrations import pending_migrations
from src.util.logger import configure_app_logging

# Named, not __name__: run with -m, that would be "__main__", outside "src".
log = logging.getLogger("src.db.migrate")

# The advisory lock that queues up concurrent runs.
_LOCK_KEY = "schema_migrations"


def migrate(conn) -> list[int]:
    """Apply every pending migration, holding the migration lock. Returns
    the versions applied."""
    conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (_LOCK_KEY,))
    try:
        pending = pending_migrations(conn)
        init_db(conn)
        return pending
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (_LOCK_KEY,))
        conn.commit()


def main() -> int:
    configure_app_logging(fmt="%(levelname)s %(name)s: %(message)s")
    conn = get_connection()
    try:
        applied = migrate(conn)
    finally:
        conn.close()
    if applied:
        log.info("Applied migrations: %s", ", ".join(str(v) for v in applied))
    else:
        log.info("Database is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
