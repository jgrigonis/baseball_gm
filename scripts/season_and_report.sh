#!/bin/bash
# scripts/season_and_report.sh
set -e
YEAR=$1
SEED_FLAG=""

# Parse optional --seed argument
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) SEED_FLAG="--seed $2"; shift 2 ;;
        *) echo "❌ Unknown argument: $1"; exit 1 ;;
    esac
done

./scripts/run_multi_season.sh -y "$YEAR" $SEED_FLAG && ./scripts/generate_report.sh -y "$YEAR"

STANDINGS_FILE="temp_files/standings.txt"
mkdir -p temp_files
> "$STANDINGS_FILE"  # truncate/create

for ((y = 2025; y <= YEAR; y++)); do
    echo "=== $y ===" >> "$STANDINGS_FILE"
    python src/league/statistics/print_standings.py -i "$y" >> "$STANDINGS_FILE"
    echo "" >> "$STANDINGS_FILE"
done

echo "✅ Standings written to $STANDINGS_FILE"
