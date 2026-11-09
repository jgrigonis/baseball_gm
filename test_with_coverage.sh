#!/bin/bash
# Run the tests under coverage, then print the coverage report (even if some
# tests failed). Exits with pytest's status.
#
#   ./run_tests_with_coverage.sh                    # every test
#   ./run_tests_with_coverage.sh tests/api -x -q    # extra arguments go to pytest
#
# Needs DATABASE_TEST_URL, a Postgres database the tests may wipe, e.g.
# postgresql://you@localhost/baseball_manager_test (or pass --db-url).
set -uo pipefail

# Run from the repo root no matter where the script is called from.
cd "$(dirname "$0")"

if [[ -z "${DATABASE_TEST_URL:-}" && " $* " != *" --db-url"* ]]; then
    echo "DATABASE_TEST_URL isn't set. Create a test database and set it, e.g.:" >&2
    echo "  createdb baseball_manager_test" >&2
    echo "  export DATABASE_TEST_URL=postgresql://$(whoami)@localhost/baseball_manager_test" >&2
    exit 1
fi

uv sync --locked --extra dev || exit 1
uv run --locked coverage run -m pytest "$@"
status=$?
uv run --locked coverage report -m
exit $status
