#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

rm leagues/league.db
# python src/league/cli.py -m small_league-2025.json
python src/league/cli.py -m world_league-2025.json -c

"$SCRIPT_DIR/clear_logs.sh"
