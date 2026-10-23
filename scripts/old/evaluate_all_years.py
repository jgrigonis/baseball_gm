# scripts/evaluate_all_years.py
import argparse
from pathlib import Path
from dataclasses import dataclass
import csv as csv_module

from src.team.team_evaluator import TeamEvaluator
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR

SKIP_FILES = {"draft.csv", "draft_results.csv"}


@dataclass
class TeamEvaluation:
    """Container for team name and evaluation."""

    filename: str
    city: str
    mascot: str
    ratings: dict[str, int]

    @property
    def display_name(self) -> str:
        return (
            f"{self.city} {self.mascot}" if self.city and self.mascot else self.filename
        )


def evaluate_directory(directory: Path) -> list[TeamEvaluation]:
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

            print(f"  ✓ Evaluated {csv_file.name}")

        except Exception as e:
            print(f"  ✗ Failed to evaluate {csv_file.name}: {e}")

    return evaluations


def calculate_averages(evaluations: list[TeamEvaluation]) -> dict[str, float]:
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

    return {
        metric: sum(e.ratings[metric] for e in evaluations) / len(evaluations)
        for metric in metrics
    }


def format_rankings(
    evaluations: list[TeamEvaluation], metric: str, title: str, top_n: int = 10
) -> str:
    sorted_teams = sorted(evaluations, key=lambda x: x.ratings[metric], reverse=True)

    lines = [
        f"\n{'=' * 60}",
        title,
        f"{'=' * 60}",
    ]

    for i, team_eval in enumerate(sorted_teams[:top_n], 1):
        lines.append(
            f"{i:2d}. {team_eval.display_name:30s} {team_eval.ratings[metric]:3d}"
        )

    return "\n".join(lines)


def format_summary(evaluations: list[TeamEvaluation]) -> str:
    averages = calculate_averages(evaluations)

    lines = [
        f"\n{'=' * 60}",
        f"LEAGUE SUMMARY ({len(evaluations)} teams)",
        f"{'=' * 60}",
        f"  Average Overall Strength:    {averages['overall_strength']:.1f}",
        f"  Average Offensive Strength:  {averages['offensive_strength']:.1f}",
        f"  Average Defensive Strength:  {averages['defensive_strength']:.1f}",
        f"  Average Pitching Strength:   {averages['pitching_strength']:.1f}",
        f"  Average Star Power:          {averages['star_power']:.1f}",
        f"  Average Depth Score:         {averages['depth_score']:.1f}",
    ]

    return "\n".join(lines)


def format_full_report(
    evaluations: list[TeamEvaluation], top_n: int = 10, year: str | None = None
) -> str:
    heading = f"{year} TEAM EVALUATION REPORT" if year else "TEAM EVALUATION REPORT"

    sections = [
        f"\n{'#' * 60}",
        heading,
        f"{'#' * 60}",
        format_summary(evaluations),
        format_rankings(
            evaluations, "overall_strength", "TOP TEAMS - OVERALL STRENGTH", top_n
        ),
        format_rankings(
            evaluations, "offensive_strength", "TOP TEAMS - OFFENSIVE STRENGTH", top_n
        ),
        format_rankings(
            evaluations, "defensive_strength", "TOP TEAMS - DEFENSIVE STRENGTH", top_n
        ),
        format_rankings(
            evaluations, "pitching_strength", "TOP TEAMS - PITCHING STRENGTH", top_n
        ),
        format_rankings(evaluations, "star_power", "TOP TEAMS - STAR POWER", top_n),
        format_rankings(evaluations, "depth_score", "TOP TEAMS - DEPTH", top_n),
        "\n",
    ]

    return "\n".join(sections)


def export_to_csv(all_evaluations: dict[str, list[TeamEvaluation]], output_path: Path):
    """Export all evaluations across all years to a single CSV."""
    with open(output_path, "w", newline="") as f:
        writer = csv_module.writer(f)
        writer.writerow(
            [
                "year",
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

        for year, evaluations in sorted(all_evaluations.items()):
            for team_eval in sorted(
                evaluations, key=lambda x: x.ratings["overall_strength"], reverse=True
            ):
                writer.writerow(
                    [
                        year,
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

    print(f"Exported CSV to {output_path}")


def find_year_directories(base_dir: Path) -> list[tuple[Path, str]]:
    """Return sorted list of (path, year_str) for all numeric subdirectories."""
    subdirs = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda d: d.name,
    )
    return [(d, d.name) for d in subdirs]


def get_args():
    parser = argparse.ArgumentParser(
        description="Evaluate teams across all year directories and write a combined report."
    )
    parser.add_argument(
        "--directory",
        "-d",
        type=str,
        default=TEAM_FILES_DIR,
        help="Base directory containing year subdirectories of team CSV files",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(Path("temp_files") / "all_years_report.txt"),
        help="Output file for the combined text report (default: temp_files/all_years_report.txt)",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=10,
        help="Number of top teams to show in each category (default: 10)",
    )
    parser.add_argument(
        "--export",
        "-e",
        type=str,
        default=str(Path("temp_files") / "all_years_results.csv"),
        help="Also export all results to a CSV file (default: temp_files/all_years_results.csv)",
    )
    return parser.parse_args()


def main():
    args = get_args()
    base_dir = Path(args.directory)

    if not base_dir.exists():
        print(f"Error: Directory {base_dir} does not exist")
        return

    year_dirs = find_year_directories(base_dir)

    if not year_dirs:
        print(f"No year subdirectories found in {base_dir}. Evaluating base directory.")
        year_dirs = [(base_dir, None)]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_evaluations: dict[str, list[TeamEvaluation]] = {}

    with open(output_path, "w") as out_file:
        for directory, year in year_dirs:
            print(f"\nEvaluating year {year or 'unknown'} ({directory})...")
            evaluations = evaluate_directory(directory)

            if not evaluations:
                print(f"  No teams found in {directory}, skipping.")
                continue

            if year:
                all_evaluations[year] = evaluations

            report = format_full_report(evaluations, top_n=args.top, year=year)
            out_file.write(report)
            print(f"  Wrote report for {year or 'unknown'} ({len(evaluations)} teams)")

    print(f"\nAll reports written to {output_path}")

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_to_csv(all_evaluations, export_path)


if __name__ == "__main__":
    main()
