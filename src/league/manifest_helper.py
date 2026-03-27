# src/league/manifest_helper.py
import json
from pathlib import Path
import random
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


def _team_dir(year, league_id: str | None = None) -> Path:
    """Return the directory for team CSV files, scoped by league if provided."""
    base = Path(TEAM_FILES_DIR) / str(year)
    return base / league_id if league_id else base


def find_missing_team_files(
    manifest: dict, league_id: str | None = None
) -> list[dict]:
    team_dir = _team_dir(manifest["season_year"], league_id)
    team_dir.mkdir(parents=True, exist_ok=True)

    missing = []
    for team in manifest["teams"]:
        path = team_dir / team["csv"]
        if not path.exists():
            missing.append(team)
    return missing


def create_team_files(
    teams: list[dict], year, rng: random.Random, league_id: str | None = None
) -> None:
    for team in teams:
        print(f"creating {team['csv']} for {team['city']} {team['mascot']}")
        create_team_from_manifest(team, year, rng=rng, league_id=league_id)


def create_team_from_manifest(
    team, year, rng: random.Random, league_id: str | None = None
) -> None:
    tf = TeamFactory(rng=rng)
    tr = tf.generate_team(city=team["city"], mascot=team["mascot"], size=26)
    PlayerCSVExporter.write(
        team=tr,
        year=year,
        filename=team["csv"],
        force_overwrite=True,
        league_id=league_id,   # PlayerCSVExporter.write needs to accept this
    )
