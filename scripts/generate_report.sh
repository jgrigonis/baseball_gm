#!/usr/bin/env bash
# scripts/generate_report.sh
# Usage: ./scripts/generate_report.sh [-y END_YEAR]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
START_YEAR=2025
END_YEAR=2026
NUM_LEADERS_TO_TRACE=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--year) END_YEAR="$2"; shift 2 ;;
        -h|--help) echo "Usage: $0 [-y END_YEAR]"; exit 0 ;;
        *) echo "❌ Unknown argument: $1"; exit 1 ;;
    esac
done

echo ""
echo "════════════════════════════════════════"
echo "  GENERATING SIM REPORT: $START_YEAR-$END_YEAR"
echo "════════════════════════════════════════"

# ── 1. Team evaluation all years ─────────────────────────────
echo ""
echo "▶ Team evaluations..."
python src/league/statistics/evaluate_all_years.py

# ── 2. League leaders range ──────────────────────────────────
echo ""
echo "▶ League leaders $START_YEAR-$END_YEAR..."
"${SCRIPT_DIR}/league_leaders_range.sh" $START_YEAR $END_YEAR

# ── 3. League totals range ───────────────────────────────────
echo ""
echo "▶ League totals $START_YEAR-$END_YEAR..."
"${SCRIPT_DIR}/league_totals_range.sh" $START_YEAR $END_YEAR

# ── Helper: leaderboards + career traces for a given year ────
trace_year_leaders() {
    local year=$1

    echo ""
    echo "════════════════════════════════════════"
    echo "  LEADERBOARDS + CAREER TRACES: $year"
    echo "════════════════════════════════════════"

    leaderboard_output=$(python src/league/statistics/view_leaderboards.py -i $year)
    echo "$leaderboard_output"

    echo ""
    echo "▶ Career traces for $year leaders..."

    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        echo ""
        echo "  ── Tracing: $name ──"
        python scripts/career_tracer.py "$name"
    done < <(echo "$leaderboard_output" | python scripts/parse_leaders.py $NUM_LEADERS_TO_TRACE)
}

# ── 4. Always trace START_YEAR leaders ───────────────────────
trace_year_leaders $START_YEAR

# ── 5. If end year > 2030, trace every 5 years ───────────────
if [[ $END_YEAR -gt 2030 ]]; then
    year=2030
    while [[ $year -le $END_YEAR ]]; do
        trace_year_leaders $year
        ((year += 5))
    done
fi

echo ""
echo "✅ Report complete: $START_YEAR-$END_YEAR"