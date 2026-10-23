#!/bin/bash
set -euo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")"

uv sync --locked --extra dev
uv run --locked coverage run -m pytest "$@"
uv run --locked coverage report -m
