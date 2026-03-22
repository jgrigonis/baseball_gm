#!/bin/bash
# scripts/season_and_report.sh
set -e
YEAR=$1
./scripts/run_multi_season.sh -y "$YEAR" && ./scripts/generate_report.sh -y "$YEAR"
