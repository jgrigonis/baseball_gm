# src/league/statistics/evaluate_team.py

import argparse
from pathlib import Path

from src.team.team_evaluator import TeamEvaluator
from src.team.team_factory import TeamFactory
from src.util.locations import TEAM_FILES_DIR


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--team", "-t", required=True, help="The team csv file to evaluate."
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    tf = TeamFactory()
    team_record = tf.from_csv(path=Path(TEAM_FILES_DIR) / args.team, city="", mascot="")
    rating_dict = TeamEvaluator.evaluate_team(team_record.players)
    print(TeamEvaluator.format_evaluation(rating_dict))


if __name__ == "__main__":
    main()
