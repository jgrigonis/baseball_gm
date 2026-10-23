# scripts/player_resolve.py
"""
Resolve a player's ID from their name, or their name from an ID.

Usage:
    python player_resolve.py "John Smith"
    python player_resolve.py --id abc123
    python player_resolve.py "John Smith" --dir team_files/2025
"""

import argparse
import csv
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Resolve player name <-> ID.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("name", nargs="?", help="Player name (partial match ok)")
    group.add_argument("--id", dest="player_id", help="Player ID to look up")
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).resolve().parent.parent / "team_files"),
        help="Directory of team CSVs",
    )
    return parser.parse_args()


def search_csvs(
    directory: Path, *, name: str | None = None, player_id: str | None = None
) -> list[dict]:
    matches = []
    for csv_path in sorted(directory.glob("**/*.csv")):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if name and name.lower() in row.get("Name", "").lower():
                    matches.append({**row, "_source_file": csv_path.name})
                elif player_id and row.get("ID", "").lower() == player_id.lower():
                    matches.append({**row, "_source_file": csv_path.name})
    return matches


def main():
    args = parse_args()
    directory = Path(args.dir)

    if not directory.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    matches = search_csvs(
        directory,
        name=args.name,
        player_id=args.player_id,
    )

    if not matches:
        query = args.name or args.player_id
        print(f"No players found matching '{query}' in {directory}")
        sys.exit(1)

    if len(matches) > 1 and args.name:
        print(f"Found {len(matches)} matches:")
        for m in matches:
            print(f"  {m['Name']:<30} {m['ID']}  ({m['_source_file']})")
    else:
        m = matches[0]
        if args.player_id:
            print(m["Name"])
        else:
            print(m["ID"])


if __name__ == "__main__":
    main()
