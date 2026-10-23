# scripts/evaluate_players.py

import argparse
import csv
import json
from pathlib import Path
from dataclasses import dataclass

from src.io.player_csv_schema import EVALUATION_CSV_HEADER, EVALUATION_RATING_COLUMNS
from src.player.player_evaluator import PlayerEvaluator
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR, MANIFEST_FILES_DIR

SKIP_FILES = {"draft.csv", "draft_results.csv"}


@dataclass
class PlayerEvaluation:
    """Container for player evaluation."""

    player_id: str
    name: str
    age: int
    position: str
    team_name: str
    ratings: dict[str, int]


def load_manifest(manifest_path: Path) -> dict:
    """
    Load and parse a league manifest file.

    Args:
        manifest_path: Path to manifest JSON file

    Returns:
        Parsed manifest dictionary

    Raises:
        FileNotFoundError: If manifest file doesn't exist
        json.JSONDecodeError: If manifest is invalid JSON
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with open(manifest_path) as f:
        return json.load(f)


def evaluate_players_from_manifest(
    manifest_path: Path, base_dir: Path | None = None
) -> list[PlayerEvaluation]:
    """
    Evaluate all players from teams listed in a manifest file.

    Args:
        manifest_path: Path to manifest JSON file
        base_dir: Base directory for CSV files (default: TEAM_FILES_DIR)

    Returns:
        List of PlayerEvaluation objects
    """
    if base_dir is None:
        base_dir = TEAM_FILES_DIR

    manifest = load_manifest(manifest_path)
    tf = TeamFactory()
    evaluations = []

    season_year = manifest.get("season_year")
    if season_year:
        year_dir = Path(base_dir) / str(season_year)
        if year_dir.exists():
            base_dir = year_dir
        else:
            print(f"  Warning: year directory {year_dir} not found, using {base_dir}")

    print(f"League: {manifest.get('league_name', 'Unknown')}")
    print(
        f"Season: {manifest.get('season_name', 'Unknown')} ({manifest.get('season_year', 'N/A')})"
    )
    print(f"Teams: {len(manifest.get('teams', []))}\n")

    for team_def in manifest.get("teams", []):
        csv_filename = team_def["csv"]
        city = team_def.get("city", "")
        mascot = team_def.get("mascot", "")
        team_name = f"{city} {mascot}".strip()

        csv_path = Path(base_dir) / csv_filename

        try:
            # Load team from CSV
            team_record = tf.from_csv(path=csv_path, city=city, mascot=mascot)

            # Evaluate each player on the team
            for player in team_record.players:
                ratings = PlayerEvaluator.rate_player(player.skills)

                evaluations.append(
                    PlayerEvaluation(
                        player_id=player.id,
                        name=player.name,
                        age=player.skills.age,
                        position=player.position,
                        team_name=team_name,
                        ratings=ratings,
                    )
                )

            print(
                f"✓ Evaluated {len(team_record.players)} players from {team_name} ({csv_filename})"
            )

        except FileNotFoundError:
            print(f"✗ File not found: {csv_path}")
        except Exception as e:
            print(f"✗ Failed to evaluate {team_name} ({csv_filename}): {e}")

    return evaluations


def print_top_players(
    evaluations: list[PlayerEvaluation], rating: str, title: str, top_n: int = 10
):
    """Print top N players for a given rating."""
    sorted_players = sorted(evaluations, key=lambda x: x.ratings[rating], reverse=True)

    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}")
    print(f"{'Rank':<6}{'Player':<25}{'Pos':<6}{'Team':<25}{'Rating':>8}")
    print(f"{'-' * 80}")

    for i, player_eval in enumerate(sorted_players[:top_n], 1):
        print(
            f"{i:<6}"
            f"{player_eval.name:<25}"
            f"{player_eval.position.upper():<6}"
            f"{player_eval.team_name:<25}"
            f"{player_eval.ratings[rating]:>8}"
        )


def print_full_report(evaluations: list[PlayerEvaluation], top_n: int = 10):
    """Print comprehensive player rankings report."""
    print(f"\n{'#' * 80}")
    print("PLAYER EVALUATION REPORT")
    print(f"{'#' * 80}")
    print(f"\nTotal Players Evaluated: {len(evaluations)}")

    # Overall rating
    print_top_players(
        evaluations, "overall_player", "TOP PLAYERS - OVERALL PLAYER", top_n
    )

    # Offensive rating
    print_top_players(
        evaluations, "overall_offense", "TOP PLAYERS - OFFENSIVE RATING", top_n
    )

    # Defensive rating
    print_top_players(
        evaluations, "defensive_value", "TOP PLAYERS - DEFENSIVE RATING", top_n
    )

    # Pitching rating
    print_top_players(evaluations, "p", "TOP PLAYERS - PITCHING RATING", top_n)

    # Speed rating
    print_top_players(evaluations, "speed_runner", "TOP PLAYERS - SPEED RATING", top_n)

    # Power rating
    print_top_players(evaluations, "power_hitter", "TOP PLAYERS - POWER RATING", top_n)

    # Contact rating
    print_top_players(
        evaluations, "contact_hitter", "TOP PLAYERS - CONTACT RATING", top_n
    )

    # Eye rating
    print_top_players(evaluations, "lead_off", "TOP PLAYERS - LEAD OFF RATING", top_n)

    print("\n")


def export_to_csv(evaluations: list[PlayerEvaluation], output_path: Path):

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(EVALUATION_CSV_HEADER)
        for player_eval in sorted(
            evaluations, key=lambda x: x.ratings["overall_player"], reverse=True
        ):
            row = [
                player_eval.name,
                player_eval.age,
                player_eval.position,
                *[
                    player_eval.ratings[rating_key]
                    for _, rating_key in EVALUATION_RATING_COLUMNS
                ],
                player_eval.team_name,
                player_eval.player_id,
            ]
            writer.writerow(row)


def get_args():
    """Get arguments from the command line."""
    parser = argparse.ArgumentParser(
        description="Evaluate all players from teams in a manifest file."
    )

    parser.add_argument(
        "--manifest",
        "-m",
        type=str,
        required=True,
        help="Manifest JSON file listing teams to evaluate",
    )

    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default=TEAM_FILES_DIR,
        help="Directory containing team CSV files (default: team_files/)",
    )

    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=10,
        help="Number of top players to show in each category (default: 10)",
    )

    parser.add_argument(
        "--export",
        "-e",
        type=str,
        help="Export results to CSV file",
    )

    return parser.parse_args()


def main():
    args = get_args()

    # Load manifest path
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = MANIFEST_FILES_DIR / manifest_path

    base_dir = Path(args.directory)

    print(f"Evaluating players from manifest: {manifest_path}")
    print(f"Base directory: {base_dir}\n")

    # Evaluate all players
    evaluations = evaluate_players_from_manifest(manifest_path, base_dir)

    if not evaluations:
        print("No players found or evaluated successfully.")
        return

    # Print full report
    print_full_report(evaluations, top_n=args.top)

    # Export if requested
    if args.export:
        export_to_csv(evaluations, Path(args.export))


if __name__ == "__main__":
    main()
