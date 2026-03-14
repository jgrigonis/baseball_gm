# scripts/evaluate_teams.py

import argparse
import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass

from src.team.team_evaluator import TeamEvaluator
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR, LEAGUE_FILES_DIR

SKIP_FILES = {"draft.csv", "draft_results.csv"}


@dataclass
class TeamEvaluation:
    """Container for team name and evaluation."""

    filename: str
    city: str
    mascot: str
    ratings: Dict[str, int]

    @property
    def display_name(self) -> str:
        return (
            f"{self.city} {self.mascot}" if self.city and self.mascot else self.filename
        )


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    with open(manifest_path, "r") as f:
        return json.load(f)


def evaluate_from_manifest(
    manifest_path: Path, base_dir: Path | None = None
) -> tuple[List[TeamEvaluation], str | None]:
    """
    Evaluate all teams listed in a manifest file.

    Returns:
        Tuple of (evaluations, year_str) where year_str comes from the manifest.
    """
    if base_dir is None:
        base_dir = TEAM_FILES_DIR

    manifest = load_manifest(manifest_path)
    tf = TeamFactory()
    evaluations = []

    year_str = str(manifest.get("season_year", "")) or None

    print(f"League: {manifest.get('league_name', 'Unknown')}")
    print(
        f"Season: {manifest.get('season_name', 'Unknown')} ({manifest.get('season_year', 'N/A')})"
    )
    print(f"Teams: {len(manifest.get('teams', []))}\n")

    for team_def in manifest.get("teams", []):
        csv_filename = team_def["csv"]
        city = team_def.get("city", "")
        mascot = team_def.get("mascot", "")

        csv_path = Path(base_dir) / csv_filename

        try:
            team_record = tf.from_csv(path=csv_path, city=city, mascot=mascot)
            ratings = TeamEvaluator.evaluate_team(team_record.players)

            evaluations.append(
                TeamEvaluation(
                    filename=csv_filename, city=city, mascot=mascot, ratings=ratings
                )
            )

            print(f"✓ Evaluated {city} {mascot} ({csv_filename})")

        except FileNotFoundError:
            print(f"✗ File not found: {csv_path}")
        except Exception as e:
            print(f"✗ Failed to evaluate {city} {mascot} ({csv_filename}): {e}")

    return evaluations, year_str


def evaluate_directory(directory: Path) -> List[TeamEvaluation]:
    """Evaluate all CSV files in a directory."""
    tf = TeamFactory()
    evaluations = []

    csv_files = sorted(f for f in directory.glob("*.csv") if f.name not in SKIP_FILES)

    for csv_file in csv_files:
        try:
            team_record = tf.from_csv(path=csv_file, city="", mascot="")
            ratings = TeamEvaluator.evaluate_team(team_record.players)

            evaluations.append(
                TeamEvaluation(
                    filename=csv_file.name, city="", mascot="", ratings=ratings
                )
            )

            print(f"✓ Evaluated {csv_file.name}")

        except Exception as e:
            print(f"✗ Failed to evaluate {csv_file.name}: {e}")

    return evaluations


def calculate_averages(evaluations: List[TeamEvaluation]) -> Dict[str, float]:
    """Calculate average ratings across all teams."""
    if not evaluations:
        return {}

    metrics = [
        "overall_strength",
        "offensive_strength",
        "defensive_strength",
        "pitching_strength",
        "star_power",
        "depth_score",
    ]

    averages = {}
    for metric in metrics:
        total = sum(eval.ratings[metric] for eval in evaluations)
        averages[metric] = total / len(evaluations)

    return averages


def print_rankings(
    evaluations: List[TeamEvaluation], metric: str, title: str, top_n: int = 10
):
    """Print top N teams for a given metric."""
    sorted_teams = sorted(evaluations, key=lambda x: x.ratings[metric], reverse=True)

    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")

    for i, team_eval in enumerate(sorted_teams[:top_n], 1):
        print(f"{i:2d}. {team_eval.display_name:30s} {team_eval.ratings[metric]:3d}")


def print_summary(evaluations: List[TeamEvaluation]):
    """Print overall summary with averages."""
    averages = calculate_averages(evaluations)

    print(f"\n{'=' * 60}")
    print(f"LEAGUE SUMMARY ({len(evaluations)} teams)")
    print(f"{'=' * 60}")
    print(f"  Average Overall Strength:    {averages['overall_strength']:.1f}")
    print(f"  Average Offensive Strength:  {averages['offensive_strength']:.1f}")
    print(f"  Average Defensive Strength:  {averages['defensive_strength']:.1f}")
    print(f"  Average Pitching Strength:   {averages['pitching_strength']:.1f}")
    print(f"  Average Star Power:          {averages['star_power']:.1f}")
    print(f"  Average Depth Score:         {averages['depth_score']:.1f}")


def print_full_report(
    evaluations: List[TeamEvaluation], top_n: int = 10, year: str | None = None
):
    """Print comprehensive rankings report."""
    heading = f"{year} TEAM EVALUATION REPORT" if year else "TEAM EVALUATION REPORT"

    print(f"\n{'#' * 60}")
    print(heading)
    print(f"{'#' * 60}")

    print_summary(evaluations)

    print_rankings(
        evaluations, "overall_strength", "TOP TEAMS - OVERALL STRENGTH", top_n
    )
    print_rankings(
        evaluations, "offensive_strength", "TOP TEAMS - OFFENSIVE STRENGTH", top_n
    )
    print_rankings(
        evaluations, "defensive_strength", "TOP TEAMS - DEFENSIVE STRENGTH", top_n
    )
    print_rankings(
        evaluations, "pitching_strength", "TOP TEAMS - PITCHING STRENGTH", top_n
    )
    print_rankings(evaluations, "star_power", "TOP TEAMS - STAR POWER", top_n)
    print_rankings(evaluations, "depth_score", "TOP TEAMS - DEPTH", top_n)

    print("\n")


def export_to_csv(evaluations: List[TeamEvaluation], output_path: Path):
    """Export all evaluations to CSV for analysis."""
    import csv

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(
            [
                "filename",
                "city",
                "mascot",
                "overall_strength",
                "offensive_strength",
                "defensive_strength",
                "pitching_strength",
                "star_power",
                "depth_score",
                "roster_size",
            ]
        )

        for team_eval in sorted(
            evaluations, key=lambda x: x.ratings["overall_strength"], reverse=True
        ):
            writer.writerow(
                [
                    team_eval.filename,
                    team_eval.city,
                    team_eval.mascot,
                    team_eval.ratings["overall_strength"],
                    team_eval.ratings["offensive_strength"],
                    team_eval.ratings["defensive_strength"],
                    team_eval.ratings["pitching_strength"],
                    team_eval.ratings["star_power"],
                    team_eval.ratings["depth_score"],
                    team_eval.ratings["roster_size"],
                ]
            )

    print(f"Exported results to {output_path}")


def pick_year_directory(base_dir: Path) -> tuple[Path, str | None]:
    """
    Find year subdirectories in base_dir.
    Auto-select if only one, prompt user if multiple.

    Returns:
        Tuple of (directory_path, year_str).
    """
    subdirs = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda d: d.name,
    )

    if not subdirs:
        return base_dir, None

    if len(subdirs) == 1:
        print(f"Using year: {subdirs[0].name}")
        return subdirs[0], subdirs[0].name

    print("Multiple seasons found:")
    for i, d in enumerate(subdirs):
        print(f"  [{i}] {d.name}")

    choice = input(f"Select [0-{len(subdirs)-1}]: ").strip()
    idx = int(choice) if choice.isdigit() and int(choice) < len(subdirs) else 0
    return subdirs[idx], subdirs[idx].name


def get_args():
    """Get arguments from the command line."""
    parser = argparse.ArgumentParser(
        description="Evaluate all teams in a directory or from a manifest file."
    )

    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default=TEAM_FILES_DIR,
        help="Directory containing team CSV files",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        type=str,
        help="Manifest JSON file listing teams to evaluate",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=10,
        help="Number of top teams to show in each category (default: 10)",
    )
    parser.add_argument("--export", "-e", type=str, help="Export results to CSV file")

    return parser.parse_args()


def main():
    args = get_args()

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = LEAGUE_FILES_DIR / manifest_path

        base_dir = Path(args.directory)

        print(f"Evaluating teams from manifest: {manifest_path}")
        print(f"Base directory: {base_dir}\n")

        evaluations, year = evaluate_from_manifest(manifest_path, base_dir)

    else:
        base_dir = Path(args.directory)
        if not base_dir.exists():
            print(f"Error: Directory {base_dir} does not exist")
            return

        directory, year = pick_year_directory(base_dir)
        print(f"Evaluating teams in {directory}...\n")
        evaluations = evaluate_directory(directory)

    if not evaluations:
        print("No teams found or evaluated successfully.")
        return

    print_full_report(evaluations, top_n=args.top, year=year)

    if args.export:
        export_to_csv(evaluations, Path(args.export))


if __name__ == "__main__":
    main()
