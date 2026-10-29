#!/bin/bash
# Delete every league (and its team_files) but keep user accounts, then start
# the web server and sim worker. Stop any running server first.
#
#   ./reset_leagues.sh         # lists the leagues and asks first
#   ./reset_leagues.sh --yes   # doesn't ask
#
# To wipe the user accounts too, use delete_db_start_webserver.sh.
set -euo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL isn't set. Set it first, e.g.:" >&2
    echo "  export DATABASE_URL=postgresql://$(whoami)@localhost/baseball_manager" >&2
    exit 1
fi

# Runs any pending migrations first. Exits non-zero if you say no, or if a
# sim is running for a league, so the server doesn't start.
uv run --locked python scripts/cligr.py reset-leagues "$@"

exec ./start_webserver.sh
