#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Parse flags ────────────────────────────────────────────────
YES=0
YEAR=2025
GAME_LOGS_FLAG=""
LOGS_FLAG=""

for arg in "$@"; do
    case "$arg" in
        -y|--yes)       YES=1 ;;
        --game_logs)    GAME_LOGS_FLAG="--game_logs" ;;
        --logs)         LOGS_FLAG="--logs" ;;
        [0-9]*)         YEAR="$arg" ;;
    esac
done

# ── Confirmation prompt (skipped with -y) ─────────────────────
if [ "$YES" -eq 0 ]; then
    printf "⚠️  Are you sure? This will destroy db and team files. [y/N] "
    read confirm
    case "$confirm" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted."; exit 1 ;;
    esac
fi

# ── Run ────────────────────────────────────────────────────────
rm -f leagues/league.db

"${SCRIPT_DIR}/delete_team_files.sh"

SEASON_ID=$(python src/league/cli.py -m world_league-${YEAR}.json -c | tee /dev/tty | grep "Season created:" | awk '{print $3}')

"${SCRIPT_DIR}/clear_logs.sh"

python src/league/play_season.py -i ${SEASON_ID} ${GAME_LOGS_FLAG}

python src/league/view_leaderboards.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/league_totals.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/league_leaders.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/playoffs/setup_playoffs.py -i ${SEASON_ID} --start-date ${YEAR}-10-01 ${LOGS_FLAG}

python src/league/playoffs/play_playoffs.py -i ${SEASON_ID} ${LOGS_FLAG}

python src/league/offseason/offseason_pipeline.py -i ${SEASON_ID}
