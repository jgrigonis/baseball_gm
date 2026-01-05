"""
This script will create many players of the given position.
You specify the position to create with the -p flag
It will then rate the players at a given position, showing
the min rating, the max rating, and the average rating.
You specify the postion to rate with the -r flag.

So, if you wanted to create outfielders, and rate them at
shortstop, you would do:

python ratings_average.py -p of -r ss

The -i flag allows you set the number of iterations to run,
the default is 100.
"""

import argparse

from src.player.positions import positions
from src.player.positions import rated_positions
from src.player.create import create


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Set the debug flag."
    )
    parser.add_argument(
        "--rating",
        "-r",
        required=True,
        choices=rated_positions,
        help="The position to rate.",
    )
    parser.add_argument(
        "--position",
        "-p",
        required=True,
        choices=positions,
        help="The position of the player to create.",
    )
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=100,
        help="The nubmer of iterations to run. (default = 100)",
    )
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    min = 100
    max = 0
    total = 0
    count = args.iterations
    if args.debug:
        my_player = create()
        print(my_player.header())
    for _ in range(count):
        my_player = create(args.position)
        p_rating = my_player.ratings[args.rating]
        total += p_rating
        if p_rating < min:
            min = p_rating
        if p_rating > max:
            max = p_rating
            if args.debug:
                print(my_player.horizontal())
    average = total / count
    print("min = {}".format(min))
    print("max = {}".format(max))
    print("avg = {}".format(average))


if __name__ == "__main__":
    main()
