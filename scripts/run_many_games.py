# scripts/run_many_games.py

import argparse

from scripts.run_game import main as game_runner


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--number", "-n", type=int, default=1, help="Set the number of games to play."
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--trace", "-t", action="store_true", help="Higher level of debugging."
    )
    parser.add_argument(
        "--pauses",
        "-p",
        action="store_true",
        help="Set the pauses flag. Implies debug.",
    )
    parser.add_argument(
        "--innings", "-i", type=int, default=9, help="Set the number of innings."
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None, help="RNG seed for reproducibility."
    )
    args = parser.parse_args()
    if args.pauses:
        args.debug = True
    return args


def main():
    args = get_args()
    results = []
    for _ in range(args.number):
        results.append(game_runner(args))

    for result in results:
        print(result)


if __name__ == "__main__":
    main()
