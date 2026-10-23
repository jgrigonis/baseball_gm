#!/bin/bash
# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate

# Default to current system user if PGUSER is unset or empty
: "${PGUSER:=$(whoami)}"

# 2. Final safety check: bail if it's still somehow empty
if [[ -z "$PGUSER" ]]; then
    echo "Error: Could not determine database user."
    exit 1
fi

# Check if --yes was passed as an argument
SKIP_CONFIRM=false
for arg in "$@"; do
  if [ "$arg" == "--yes" ]; then
    SKIP_CONFIRM=true
  fi
done

# If not skipping, ask the user
if [ "$SKIP_CONFIRM" = false ]; then
    read -p "Are you sure you want to reset the DB and start? [y/n]: " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# clear team_files
rm -rf team_files/*

# echo "$PGUSER"
# Do the needful
psql -U "$PGUSER" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'baseball_manager';" postgres
psql -U "$PGUSER" -c "DROP DATABASE baseball_manager;" postgres
psql -U "$PGUSER" -c "CREATE DATABASE baseball_manager;" postgres

uvicorn src.api.main:app --reload
