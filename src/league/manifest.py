import json


def load_manifest(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def validate_manifest(manifest):
    try:
        assert "league_name" in manifest
    except AssertionError:
        print("league_name not found in league manifest")
        quit(1)
    try:
        assert "teams" in manifest
    except AssertionError:
        print("teams section not found in league manifest")
        quit(1)
    for team in manifest["teams"]:
        for key in ("csv", "city", "mascot"):
            try:
                assert key in team
            except AssertionError:
                print(f"{key} info not found in a team section")
                quit(1)
    find_duplicates(manifest)


def find_duplicates(manifest):
    csvs = []
    city_mascot = []
    for team in manifest["teams"]:
        csvs.append(team["csv"])
        city_mascot.append((team["city"], team["mascot"]))
    try:
        assert len(csvs) == len(set(csvs))
    except AssertionError:
        print("Duplicate csv files found in league manifest")
        quit(1)
    try:
        assert len(city_mascot) == len(set(city_mascot))
    except AssertionError:
        print("Duplicate City/Mascot combinations found in league manifest")
        quit(1)
