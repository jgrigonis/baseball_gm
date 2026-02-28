"""
Scan all team CSV files and report stamina (ST) distribution.

Usage:
    python check_stamina.py                        # scans ./team_files/
    python check_stamina.py team_files/2025        # specific season dir
    python check_stamina.py team_files/2025 --pos sp  # pitchers only
"""

import csv
import sys
from pathlib import Path
from collections import defaultdict

STAMINA_COL = "ST"
POSITION_COL = "PS"


def scan_directory(directory: Path, position_filter: str | None = None):
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {directory}")
        return

    all_stamina = []
    by_team = {}
    skipped = []

    for path in csv_files:
        team_stamina = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if STAMINA_COL not in (reader.fieldnames or []):
                skipped.append(path.name)
                continue
            for row in reader:
                if position_filter and row.get(POSITION_COL, "").lower() != position_filter.lower():
                    continue
                try:
                    st = int(row[STAMINA_COL])
                    team_stamina.append(st)
                    all_stamina.append(st)
                except (ValueError, KeyError):
                    pass

        if team_stamina:
            by_team[path.stem] = team_stamina

    if not all_stamina:
        print("No stamina values found.")
        return

    label = f" (position={position_filter})" if position_filter else ""
    print(f"\n{'='*55}")
    print(f"  Stamina Report{label}")
    print(f"  Directory: {directory}")
    print(f"  Files scanned: {len(csv_files)}  |  Players: {len(all_stamina)}")
    print(f"{'='*55}")

    print(f"\n{'LEAGUE-WIDE SUMMARY':}")
    print(f"  Min:    {min(all_stamina)}")
    print(f"  Max:    {max(all_stamina)}")
    print(f"  Avg:    {sum(all_stamina)/len(all_stamina):.1f}")
    print(f"  Median: {sorted(all_stamina)[len(all_stamina)//2]}")

    # Bucket distribution
    buckets = {"1-30": 0, "31-50": 0, "51-70": 0, "71-90": 0, "91-100": 0}
    for v in all_stamina:
        if v <= 30:    buckets["1-30"] += 1
        elif v <= 50:  buckets["31-50"] += 1
        elif v <= 70:  buckets["51-70"] += 1
        elif v <= 90:  buckets["71-90"] += 1
        else:          buckets["91-100"] += 1

    print(f"\n  Distribution:")
    for bucket, count in buckets.items():
        bar = "█" * (count * 30 // len(all_stamina))
        print(f"    {bucket:8s}  {count:4d}  {bar}")

    # Per-team summary
    print(f"\n{'TEAM BREAKDOWN':}")
    print(f"  {'Team':<28} {'Count':>5}  {'Min':>4}  {'Avg':>5}  {'Max':>4}")
    print(f"  {'-'*52}")
    for team, values in sorted(by_team.items()):
        avg = sum(values) / len(values)
        print(f"  {team:<28} {len(values):>5}  {min(values):>4}  {avg:>5.1f}  {max(values):>4}")

    if skipped:
        print(f"\n  Skipped (no ST column): {', '.join(skipped)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    directory = Path(args[0]) if args else Path("team_files")
    pos_filter = None
    if "--pos" in args:
        idx = args.index("--pos")
        pos_filter = args[idx + 1]

    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    scan_directory(directory, pos_filter)
