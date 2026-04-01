# scripts/create_more_seasons.py
import argparse
import json
from pathlib import Path

from src.util.locations import MANIFEST_FILES_DIR

BASE_FILE = "world_league-2025.json"
NUM_FILES = 50  # how many future manifests to create


def parse_args():
    p = argparse.ArgumentParser(description="Create Manifest files for multiple years.")
    p.add_argument(
        "--number",
        "-n",
        default=NUM_FILES,
        help="The number of new manifest files to create",
    )
    p.add_argument(
        "--file", "-f", default=BASE_FILE, help="The base filename to use as template"
    )
    p.add_argument("--year", "-y", default=2025, help="The base filename's year'")
    p.add_argument(
        "--overwrite",
        "-o",
        action="store_true",
        help="Overwrite existing manifest files",
    )
    return p.parse_args()


def create_manifests(args):
    with open(
        Path(MANIFEST_FILES_DIR) / str(args.file + "-" + str(args.year) + ".json")
    ) as f:
        data = json.load(f)

    base_year = data["season_year"]

    # Extract the season number from "Season 1"
    base_season = int(data["season_name"].split()[1])

    for i in range(1, args.number + 1):
        new_year = base_year + i
        new_season = base_season + i

        new_data = data.copy()
        new_data["season_year"] = new_year
        new_data["season_name"] = f"Season {new_season}"

        filename = f"{args.file}-{new_year}.json"

        full_path = Path(MANIFEST_FILES_DIR) / filename
        if not full_path.exists() or args.overwrite:
            with open(full_path, "w") as f:
                json.dump(new_data, f, indent=2)

            print(f"Created {filename}")


def main():
    args = parse_args()
    create_manifests(args)


if __name__ == "__main__":
    main()
