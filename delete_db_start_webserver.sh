#!/bin/bash
# Wipe everything and start fresh: drop and recreate the database DATABASE_URL
# names (every league and every user account goes), delete every league's
# team_files, then start the web server and sim worker on the empty database.
#
#   ./delete_db_start_webserver.sh         # asks first
#   ./delete_db_start_webserver.sh --yes   # doesn't ask
#
# To keep user accounts and only delete the leagues, use reset_leagues.sh.
set -euo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")"

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL isn't set. Set it first, e.g.:" >&2
    echo "  export DATABASE_URL=postgresql://$(whoami)@localhost/baseball_manager" >&2
    exit 1
fi

if [[ "${1:-}" != "--yes" && "${1:-}" != "-y" ]]; then
    read -r -p "Delete the whole database (every league and user account) and start fresh? [y/N]: " confirm
    if [[ ! $confirm =~ ^[Yy]([Ee][Ss])?$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Disconnects anything still using the database, e.g. a server left running.
uv run --locked python scripts/cligr.py clear --db --all-teams --yes

# Creates the tables and the admin login, then starts the server and worker.
exec ./start_webserver.sh
