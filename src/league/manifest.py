import json


def load_manifest(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def validate_manifest(manifest):
    assert "league_name" in manifest
    assert "teams" in manifest
    for team in manifest["teams"]:
        for key in ("csv", "city", "mascot"):
            assert key in team
