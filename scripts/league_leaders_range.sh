#!/usr/bin/env bash
# scripts/leage_leaders_range.sh

set -e
set -o pipefail

# Usage: ./league_leaders_range.sh 2025 2035

START_YEAR=${1:?Usage: $0 START_YEAR END_YEAR}
END_YEAR=${2:?Usage: $0 START_YEAR END_YEAR}

DB_FILE="cli.db"

OUTPUT="temp_files/league_leaders_${START_YEAR}_${END_YEAR}.txt"
mkdir -p temp_files

> "$OUTPUT"  # clear/create file

for (( YEAR=START_YEAR; YEAR<=END_YEAR; YEAR++ )); do
    echo "Processing $YEAR..."
    python src/league/statistics/league_leaders.py -i "$YEAR" -f {DB_FILE} >> "$OUTPUT"
done

echo "✅ Done — output saved to $OUTPUT"
