#!/bin/bash
# Start the dev web server with a sim worker beside it, after bringing the
# database schema up to date. Ctrl-C stops both.
#
#   ./start_webserver.sh               # http://127.0.0.1:8000, reloads on code changes
#   ./start_webserver.sh --port 8080   # extra arguments go to uvicorn
#
# Needs DATABASE_URL, e.g. postgresql://you@localhost/baseball_manager, and the
# database itself (delete_db_start_webserver.sh creates it).
set -euo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL isn't set. Set it first, e.g.:" >&2
    echo "  export DATABASE_URL=postgresql://$(whoami)@localhost/baseball_manager" >&2
    exit 1
fi

# `uv run` installs anything uv.lock has that .venv is missing.
uv run --locked python -m src.db.migrate

# The sim worker runs the sims the server queues (src/worker.py). It doesn't
# reload on code changes the way the server does; it restarts with this
# script.
uv run --locked python -m src.worker &
WORKER_PID=$!
# Don't leave the worker behind if this script is killed.
trap 'kill -TERM "$WORKER_PID" 2>/dev/null' EXIT

# In production, leave out --reload.
status=0
uv run --locked uvicorn src.api.main:app --reload "$@" || status=$?

# The server stopped (Ctrl-C, or it couldn't start). Stop the worker, letting it finish a sim it's
# in the middle of, unless Ctrl-C is pressed again.
echo "Stopping the sim worker (it finishes a running sim first; Ctrl-C again to stop it now)..."
# The worker is a child of `uv run`, which can't pass on a SIGKILL.
trap 'pkill -KILL -P "$WORKER_PID"; kill -KILL "$WORKER_PID" 2>/dev/null' INT
kill -TERM "$WORKER_PID" 2>/dev/null
while kill -0 "$WORKER_PID" 2>/dev/null; do
    wait "$WORKER_PID" 2>/dev/null
done
exit "$status"
