#!/bin/bash
set -euo pipefail

python -m pip install -e ".[dev]"
python -m coverage run -m pytest "$@"
python -m coverage report -m
