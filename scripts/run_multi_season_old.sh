#!/bin/sh

# run_multi_season.sh
# Initializes a new league and runs consecutive seasons.
#
# Usage:
#   ./scripts/run_multi_season.sh [--game_logs] [--logs]
#
# Runs:
#   new_league.sh -y       (2025 base year, no prompt)
#   run_season.sh 2026
#   run_season.sh 2027
#   run_season.sh 2028
#   run_season.sh 2029

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Parse flags ────────────────────────────────────────────────
GAME_LOGS_FLAG=""
LOGS_FLAG=""

for arg in "$@"; do
    case "$arg" in
        --game_logs)    GAME_LOGS_FLAG="--game_logs" ;;
        --logs)         LOGS_FLAG="--logs" ;;
    esac
done

set -e  # abort on any failure

# ── New league (bypass prompt) ─────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Initializing new league (2025)"
echo "════════════════════════════════════════"
"${SCRIPT_DIR}/new_league.sh" -y ${GAME_LOGS_FLAG} ${LOGS_FLAG}

# ── Run seasons ────────────────────────────────────────────────
for YEAR in 2026 2027 2028 2029; do
    echo ""
    echo "════════════════════════════════════════"
    echo "  Running season: $YEAR"
    echo "════════════════════════════════════════"
    "${SCRIPT_DIR}/run_season.sh" "$YEAR" ${GAME_LOGS_FLAG} ${LOGS_FLAG}
done

echo ""
echo "✅  All seasons complete (2025–2029)."