#!/usr/bin/env bash
# sscripts/run_season.sh

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

caffeinate -i

# ── Parse flags ────────────────────────────────────────────────
YEAR=2025
GAME_LOGS_FLAG=""
LOGS_FLAG=""
SEED_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --game_logs)    GAME_LOGS_FLAG="--logs" ; shift ;;
        --logs)         LOGS_FLAG="--logs" ; shift ;;
        --seed)         SEED_FLAG="--seed $2" ; shift 2 ;;
        [0-9]*)         YEAR="$1" ; shift ;;
        *)              echo "❌ Unknown argument: $1" ; exit 1 ;;
    esac
done

# ── Run ────────────────────────────────────────────────────────
SEASON_ID=$(python src/league/cli.py -m world_league-${YEAR}.json -c --update-rosters | tee /dev/tty | grep "Season created:" | awk '{print $3}')

if [[ -z "$SEASON_ID" ]]; then
    echo "❌ Failed to create season — check output above"
    exit 1
fi

python src/league/play_season.py -i ${SEASON_ID} ${SEED_FLAG} ${GAME_LOGS_FLAG}

python src/league/statistics/view_leaderboards.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/statistics/league_totals.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/statistics/league_leaders.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/playoffs/setup_playoffs.py -i ${SEASON_ID} --start-date ${YEAR}-10-01 ${LOGS_FLAG}

python src/league/playoffs/play_playoffs.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/offseason/offseason_pipeline.py -i ${SEASON_ID}
