# src/league/manifest_helper.py
import json
from pathlib import Path
import sys

from src.io.player_csv_exporter import PlayerCSVExporter
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR


def load_manifest(path: str) -> dict:
    """Open and load the manifest file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)


def validate_manifest_structure(manifest: dict) -> None:
    if "league_name" not in manifest:
        raise ValueError("league_name not found in league manifest")

    if "teams" not in manifest:
        raise ValueError("teams section not found in league manifest")

    for team in manifest["teams"]:
        for key in ("csv", "city", "mascot"):
            if key not in team:
                raise ValueError(f"{key} missing from team entry")


def validate_manifest_uniqueness(manifest: dict) -> None:
    csvs = [team["csv"] for team in manifest["teams"]]
    if len(csvs) != len(set(csvs)):
        raise ValueError("Duplicate csv files found in league manifest")

    combos = [(t["city"], t["mascot"]) for t in manifest["teams"]]
    if len(combos) != len(set(combos)):
        raise ValueError("Duplicate City/Mascot combinations found")


def find_missing_team_files(manifest: dict) -> list[dict]:
    missing = []
    for team in manifest["teams"]:
        path = Path(TEAM_FILES_DIR) / team["csv"]
        if not path.exists():
            missing.append(team)
    return missing


def create_team_files(teams: list[dict]) -> None:
    for team in teams:
        print(f"creating {team['csv']} for {team['city']} {team['mascot']}")
        create_team_from_manifest(team)


def create_team_from_manifest(team):
    tf = TeamFactory()
    tr = tf.generate_team(city=team["city"], mascot=team["mascot"])
    PlayerCSVExporter.write(team=tr, filename=team["csv"])
