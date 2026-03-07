#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# First arg is year (default 2025), rest are flags
YEAR=${1:-2025}
shift 2>/dev/null  # shift off the year arg if present, ignore error if no args

# Pass --logs through to play_season if provided
GAME_LOGS_FLAG=""
for arg in "$@"; do
    if [ "$arg" = "--game_logs" ]; then
        GAME_LOGS_FLAG="--game_logs"
    fi
done

rm leagues/league.db

SEASON_ID=$(python src/league/cli.py -m world_league-${YEAR}.json -c | tee /dev/tty | grep "Season created:" | awk '{print $3}')

"$SCRIPT_DIR/clear_logs.sh"

python src/league/play_season.py -i $SEASON_ID $GAME_LOGS_FLAG

python src/league/view_leaderboards.py -i $SEASON_ID --logs

python src/league/league_totals.py -i $SEASON_ID --logs

python src/league/league_leaders.py -i $SEASON_ID --logs

python src/league/playoffs/setup_playoffs.py -i $SEASON_ID --start-date ${YEAR}-10-01 --logs

python src/league/playoffs/play_playoffs.py -i $SEASON_ID --logs

python src/league/offseason/offseason_pipeline.py -i $SEASON_ID

