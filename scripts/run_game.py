# scripts/run_game.py

"""
Run one game.

Create 2 random teams

Make them play.

We can discard the results.

"""

import argparse
import logging
import random
import uuid

from src.game.game import Game
from src.team.team_factory import TeamFactory
from src.team.team_in_game_factory import TeamInGameFactory

from src.util.logger import setup_logger

HOME_CITY = "Huntsville"
HOME_MASCOT = "Hornets"
AWAY_CITY = "Athens"
AWAY_MASCOT = "Aces"


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
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
    return args


def cli():
    return main(get_args())


def main(args):
    # print(args)
    # args = get_args()
    levl = logging.INFO
    if args.debug:
        levl = logging.DEBUG
    if args.trace:
        levl = logging.TRACE
    logger = setup_logger(
        name="game", level=levl, console_level=levl, log_id=str(uuid.uuid4())
    )
    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    print(f"🎲 Seed: {seed}")  # always print so you can replay
    rng = random.Random(seed)

    tf = TeamFactory(log_level=levl, rng=rng)
    # Set up Home Team Record
    home_team_record = tf.generate_team(city=HOME_CITY, mascot=HOME_MASCOT)

    # Set up Away Team Record
    away_team_record = tf.generate_team(city=AWAY_CITY, mascot=AWAY_MASCOT)

    # setup TeamInGame objects
    home_team = TeamInGameFactory.from_record(home_team_record)
    away_team = TeamInGameFactory.from_record(away_team_record)

    # set lineups
    home_team.set_lineup()
    away_team.set_lineup()

    print(home_team.output_lineup_ratings())
    print(home_team.output_pitcher_ratings())
    print(away_team.output_lineup_ratings())
    print(away_team.output_pitcher_ratings())

    print(home_team.output_lineup_skills())
    print(home_team.output_pitcher_skills())
    print(away_team.output_lineup_skills())
    print(away_team.output_pitcher_skills())

    my_game = Game(
        home_team=home_team,
        away_team=away_team,
        logger=logger,
        pauses=args.pauses,
        rng=rng,
    )
    result = my_game.play()
    # Pitching decisions
    d = my_game.decisions
    if d:
        if d.win:
            print(f"✅ Win:  {d.win.pitcher.name}")
        if d.loss:
            print(f"❌ Loss: {d.loss.pitcher.name}")
        if d.save:
            print(f"🔒 Save: {d.save.pitcher.name}")

    print(home_team.output_defensive_stats())
    print(away_team.output_defensive_stats())

    print(home_team.output_lineup_ratings())
    print(home_team.output_pitcher_ratings())
    print(away_team.output_lineup_ratings())
    print(away_team.output_pitcher_ratings())

    print(home_team.output_lineup_skills())
    print(home_team.output_pitcher_skills())
    print(away_team.output_lineup_skills())
    print(away_team.output_pitcher_skills())

    print(home_team.output_batting_stats())
    print(away_team.output_batting_stats())

    print(home_team.output_pitching_stats())
    print(away_team.output_pitching_stats())


    return result


if __name__ == "__main__":
    cli()
