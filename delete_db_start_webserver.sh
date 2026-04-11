#!/bin/bash
source .venv/bin/activate

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

# Do the needful
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'your_db_name';" postgres
psql -c "DROP DATABASE baseball_manager;"
psql -c "CREATE DATABASE baseball_manager;"

uvicorn src.api.main:app --reload
