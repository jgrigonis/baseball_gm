#!/usr/bin/env bash
# scripts/new_league.sh

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_FILE="cli.db"

# ── Parse flags ────────────────────────────────────────────────
YES=0
YEAR=2025
SEED=""
GAME_LOGS_FLAG=""
LOGS_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)    YES=1; shift ;;
        --year)      YEAR="$2"; shift 2 ;;
        --game_logs) GAME_LOGS_FLAG="--logs"; shift ;;
        --logs)      LOGS_FLAG="--logs"; shift ;;
        --seed)      SEED="$2"; shift 2 ;;
        *)           echo "❌ Unknown argument: $1"; exit 1 ;;
    esac
done

SEED_FLAG=""
CLI_SEED_FLAG=""
if [[ -n "$SEED" ]]; then
    SEED_FLAG="--seed $SEED"
    CLI_SEED_FLAG="--seed $SEED"
fi

# ── Confirmation prompt (skipped with -yes) ─────────────────────
if [[ "$YES" -eq 0 ]]; then
    printf "⚠️  Are you sure? This will destroy db. [y/N] "
    read confirm
    case "$confirm" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted."; exit 1 ;;
    esac
fi

# ── Run ────────────────────────────────────────────────────────
rm -f leagues/${DB_FILE}

SEASON_ID=$(python src/league/cli.py -m world_league-${YEAR}.json -c ${CLI_SEED_FLAG} | tee /dev/tty | grep "Season created:" | awk '{print $3}')

"${SCRIPT_DIR}/clear_logs.sh"

"${SCRIPT_DIR}/clear_temp_files.sh"

python src/league/play_season.py -i ${SEASON_ID} ${SEED_FLAG} ${GAME_LOGS_FLAG} --db ${DB_FILE}

python src/league/statistics/view_leaderboards.py -i ${SEASON_ID} ${LOGS_FLAG} -f ${DB_FILE}

python src/league/statistics/league_totals.py -i ${SEASON_ID} ${LOGS_FLAG} -f ${DB_FILE}

python src/league/statistics/league_leaders.py -i ${SEASON_ID} ${LOGS_FLAG} -f ${DB_FILE}

python src/league/playoffs/setup_playoffs.py -i ${SEASON_ID} --start-date ${YEAR}-10-01 ${LOGS_FLAG} --db ${DB_FILE}

python src/league/playoffs/play_playoffs.py -i ${SEASON_ID} ${LOGS_FLAG} --db ${DB_FILE}

python src/league/offseason/offseason_pipeline.py -i ${SEASON_ID} ${SEED_FLAG} --db ${DB_FILE}
