#!/usr/bin/env bash

# run_multi_season.sh
#
# Usage:
#   ./scripts/run_multi_season.sh [options]
#
# Options:
#   -y, --year YEAR     Run seasons until YEAR (default: 2026)
#   --game_logs         Enable game logs
#   --logs              Enable logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

START_YEAR=2026
END_YEAR=2026

GAME_LOGS_FLAG=""
LOGS_FLAG=""

caffeinate -i

# ── Parse arguments ───────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--year)
            END_YEAR="$2"
            shift 2
            ;;
        --seed)
            SEED_FLAG="--seed $2"
            shift 2
            ;;
        --game_logs)
            GAME_LOGS_FLAG="--logs"
            shift
            ;;
        --logs)
            LOGS_FLAG="--logs"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-y YEAR] [--game_logs] [--logs]"
            exit 0
            ;;
        *)
            echo "❌ Unknown argument: $1"
            echo "Usage: $0 [-y YEAR] [--game_logs] [--logs]"
            exit 1
            ;;
    esac
done

set -e

# ── New league ────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Initializing new league (2025)"
echo "════════════════════════════════════════"

"${SCRIPT_DIR}/new_league.sh" -y ${SEED_FLAG} ${GAME_LOGS_FLAG} ${LOGS_FLAG}

# ── Run seasons ───────────────────────────────────────────────
YEAR=$START_YEAR

while [[ "$YEAR" -le "$END_YEAR" ]]; do
    echo ""
    echo "════════════════════════════════════════"
    echo "  Running season: $YEAR"
    echo "════════════════════════════════════════"

    "${SCRIPT_DIR}/run_season.sh" "$YEAR" ${SEED_FLAG} ${GAME_LOGS_FLAG} ${LOGS_FLAG}

    ((YEAR++))
done

echo ""
echo "✅  All seasons complete (2025–${END_YEAR})."