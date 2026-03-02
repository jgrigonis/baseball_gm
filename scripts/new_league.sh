#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

rm leagues/league.db

SEASON_ID=$(python src/league/cli.py -m world_league-2025.json -c | tee /dev/tty | grep "Season created:" | awk '{print $3}')

"$SCRIPT_DIR/clear_logs.sh"

python src/league/play_season.py -i $SEASON_ID --logs

python scripts/view_leaderboards.py -i $SEASON_ID

python scripts/league_totals.py -i $SEASON_ID

