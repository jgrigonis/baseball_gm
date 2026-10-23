#!/bin/bash
set -euo pipefail

uv sync --locked --extra dev
uv run --locked coverage run -m pytest "$@"
uv run --locked coverage report -m
