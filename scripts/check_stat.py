"""
Scan all team CSV files and report stat (ST) distribution.

Usage:
    python check_stat.py --stat ST                       # scans ./team_files/ for ST column
    python check_stat.py team_files/2025 --stat ST       # specific dir for SP column
    python check_stat.py --pos sp --stat AC              # e.g. sp for starting pitcher and AC for accuracy
"""

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

from src.player.positions import AFFINITY_POSITIONS
from src.player.player_formatters import CSV_FIELDS

POSITION_COL = "PS"

def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", "-d", help="Set the directory to scan.", default="team_files")
    parser.add_argument(
        "--pos", "-p", choices=AFFINITY_POSITIONS, help="Set the position to filter on."
    )
    parser.add_argument(
        "--stat", "-s", choices=CSV_FIELDS, help="Set the stat to filter on."
    )
    args = parser.parse_args()
    return args


def scan_directory(directory: Path, position_filter: str | None = None, stat_filter: str | None = None):
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {directory}")
        return

    all_stat = []
    by_team = {}
    skipped = []

    for path in csv_files:
        team_stat = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if stat_filter not in (reader.fieldnames or []):
                skipped.append(path.name)
                continue
            for row in reader:
                if position_filter and row.get(POSITION_COL, "").lower() != position_filter.lower():
                    continue
                try:
                    st = int(row[stat_filter])
                    team_stat.append(st)
                    all_stat.append(st)
                except (ValueError, KeyError):
                    pass

        if team_stat:
            by_team[path.stem] = team_stat

    if not all_stat:
        print("No stat values found.")
        return

    label = f" (position={position_filter})" if position_filter else ""
    print(f"\n{'='*55}")
    print(f"  Stat Report{label}")
    print(f"  Directory: {directory}")
    print(f"  Files scanned: {len(csv_files)}  |  Players: {len(all_stat)}")
    print(f"{'='*55}")

    print(f"\n{'LEAGUE-WIDE SUMMARY':}")
    print(f"  Min:    {min(all_stat)}")
    print(f"  Max:    {max(all_stat)}")
    print(f"  Avg:    {sum(all_stat)/len(all_stat):.1f}")
    print(f"  Median: {sorted(all_stat)[len(all_stat)//2]}")

    # Bucket distribution
    buckets = {"1-30": 0, "31-50": 0, "51-70": 0, "71-90": 0, "91-100": 0}
    for v in all_stat:
        if v <= 30:    buckets["1-30"] += 1
        elif v <= 50:  buckets["31-50"] += 1
        elif v <= 70:  buckets["51-70"] += 1
        elif v <= 90:  buckets["71-90"] += 1
        else:          buckets["91-100"] += 1

    print(f"\n  Distribution:")
    for bucket, count in buckets.items():
        bar = "█" * (count * 30 // len(all_stat))
        print(f"    {bucket:8s}  {count:4d}  {bar}")

    # Per-team summary
    print(f"\n{'TEAM BREAKDOWN':}")
    print(f"  {'Team':<28} {'Count':>5}  {'Min':>4}  {'Avg':>5}  {'Max':>4}")
    print(f"  {'-'*52}")
    for team, values in sorted(by_team.items()):
        avg = sum(values) / len(values)
        print(f"  {team:<28} {len(values):>5}  {min(values):>4}  {avg:>5.1f}  {max(values):>4}")

    if skipped:
        print(f"\n  Skipped (no STAT column): {', '.join(skipped)}")


if __name__ == "__main__":
    args = get_args()
    directory = Path(args.directory) if args.directory else Path("team_files")
    pos_filter = args.pos
    stat_filter = args.stat
    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    scan_directory(directory, pos_filter, stat_filter)
