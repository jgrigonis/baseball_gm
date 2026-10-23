#!/bin/bash
# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
uvicorn src.api.main:app --reload
# uvicorn src.api.main:app
# In production you would remove the --reload 
