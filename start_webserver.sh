#!/bin/bash
# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
python -m src.db.migrate || exit 1
# The sim worker runs the sims the server queues (src/worker.py). It stops
# with the server.
python -m src.worker &
WORKER_PID=$!
trap 'kill $WORKER_PID 2>/dev/null' EXIT
uvicorn src.api.main:app --reload
# uvicorn src.api.main:app
# In production you would remove the --reload 
