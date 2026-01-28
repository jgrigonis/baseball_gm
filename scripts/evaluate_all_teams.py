# scripts/evaluate_all_teams.py

import argparse
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass

from src.team.team_evaluator import TeamEvaluator
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR


@dataclass
class TeamEvaluation:
    """Container for team name and evaluation."""
    filename: str
    city: str
    mascot: str
    ratings: Dict[str, int]
    
    @property
    def display_name(self) -> str:
        return f"{self.city} {self.mascot}" if self.city and self.mascot else self.filename


def evaluate_directory(directory: Path) -> List[TeamEvaluation]:
    """Evaluate all CSV files in a directory."""
    tf = TeamFactory()
    evaluations = []
    
    csv_files = sorted(directory.glob("*.csv"))
    
    for csv_file in csv_files:
        try:
            # Parse city/mascot from filename if needed
            # For now, just use filename
            team_record = tf.from_csv(
                path=csv_file,
                city="",
                mascot=""
            )
            
            ratings = TeamEvaluator.evaluate_team(team_record.players)
            
            evaluations.append(TeamEvaluation(
                filename=csv_file.name,
                city="",
                mascot="",
                ratings=ratings
            ))
            
            print(f"✓ Evaluated {csv_file.name}")
            
        except Exception as e:
            print(f"✗ Failed to evaluate {csv_file.name}: {e}")
    
    return evaluations


def calculate_averages(evaluations: List[TeamEvaluation]) -> Dict[str, float]:
    """Calculate average ratings across all teams."""
    if not evaluations:
        return {}
    
    metrics = [
        'overall_strength',
        'offensive_strength', 
        'defensive_strength',
        'pitching_strength',
        'star_power',
        'depth_score'
    ]
    
    averages = {}
    for metric in metrics:
        total = sum(eval.ratings[metric] for eval in evaluations)
        averages[metric] = total / len(evaluations)
    
    return averages


def print_rankings(evaluations: List[TeamEvaluation], metric: str, title: str, top_n: int = 10):
    """Print top N teams for a given metric."""
    sorted_teams = sorted(
        evaluations,
        key=lambda x: x.ratings[metric],
        reverse=True
    )
    
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


def print_full_report(evaluations: List[TeamEvaluation], top_n: int = 10):
    """Print comprehensive rankings report."""
    print(f"\n{'#' * 60}")
    print(f"TEAM EVALUATION REPORT")
    print(f"{'#' * 60}")
    
    # Overall summary
    print_summary(evaluations)
    
    # Rankings for each category
    print_rankings(evaluations, 'overall_strength', 'TOP TEAMS - OVERALL STRENGTH', top_n)
    print_rankings(evaluations, 'offensive_strength', 'TOP TEAMS - OFFENSIVE STRENGTH', top_n)
    print_rankings(evaluations, 'defensive_strength', 'TOP TEAMS - DEFENSIVE STRENGTH', top_n)
    print_rankings(evaluations, 'pitching_strength', 'TOP TEAMS - PITCHING STRENGTH', top_n)
    print_rankings(evaluations, 'star_power', 'TOP TEAMS - STAR POWER', top_n)
    print_rankings(evaluations, 'depth_score', 'TOP TEAMS - DEPTH', top_n)
    
    print("\n")


def export_to_csv(evaluations: List[TeamEvaluation], output_path: Path):
    """Export all evaluations to CSV for analysis."""
    import csv
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'filename',
            'overall_strength',
            'offensive_strength',
            'defensive_strength',
            'pitching_strength',
            'star_power',
            'depth_score',
            'roster_size'
        ])
        
        # Data
        for team_eval in sorted(evaluations, key=lambda x: x.ratings['overall_strength'], reverse=True):
            writer.writerow([
                team_eval.filename,
                team_eval.ratings['overall_strength'],
                team_eval.ratings['offensive_strength'],
                team_eval.ratings['defensive_strength'],
                team_eval.ratings['pitching_strength'],
                team_eval.ratings['star_power'],
                team_eval.ratings['depth_score'],
                team_eval.ratings['roster_size']
            ])
    
    print(f"Exported results to {output_path}")


def get_args():
    """Get arguments from the command line."""
    parser = argparse.ArgumentParser(
        description="Evaluate all teams in a directory and show rankings."
    )
    parser.add_argument(
        "--directory", "-d",
        default=str(TEAM_FILES_DIR),
        help="Directory containing team CSV files (default: TEAM_FILES_DIR)"
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=10,
        help="Number of top teams to show in each category (default: 10)"
    )
    parser.add_argument(
        "--export", "-e",
        help="Export results to CSV file"
    )
    
    return parser.parse_args()


def main():
    args = get_args()
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"Error: Directory {directory} does not exist")
        return
    
    print(f"Evaluating teams in {directory}...\n")
    
    # Evaluate all teams
    evaluations = evaluate_directory(directory)
    
    if not evaluations:
        print("No teams found or evaluated successfully.")
        return
    
    # Print full report
    print_full_report(evaluations, top_n=args.top)
    
    # Export if requested
    if args.export:
        export_to_csv(evaluations, Path(args.export))


if __name__ == "__main__":
    main()
