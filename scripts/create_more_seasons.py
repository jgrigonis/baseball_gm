import json
import os
from pathlib import Path

LEAGUE_FILES_DIR = "leagues"
BASE_FILE = "world_league-2025.json"
NUM_FILES = 50  # how many future manifests to create

with open(LEAGUE_FILES_DIR + os.sep + BASE_FILE) as f:
    data = json.load(f)

base_year = data["season_year"]

# Extract the season number from "Season 1"
base_season = int(data["season_name"].split()[1])

for i in range(1, NUM_FILES + 1):
    new_year = base_year + i
    new_season = base_season + i

    new_data = data.copy()
    new_data["season_year"] = new_year
    new_data["season_name"] = f"Season {new_season}"

    filename = f"world_league-{new_year}.json"

    with open(LEAGUE_FILES_DIR + os.sep + filename, "w") as f:
        json.dump(new_data, f, indent=2)

    print(f"Created {filename}")
