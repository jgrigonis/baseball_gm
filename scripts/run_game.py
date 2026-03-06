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
    parser.add_argument("--home", default=None, help="Home Team Record")
    parser.add_argument("--away", "-a", default=None, help="Away Team Record")
    args = parser.parse_args()
    return args


def cli():
    return main(get_args())


def main(args):
    # logger.info(args)
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
    logger.info(f"🎲 Seed: {seed}")  # always logger.info so you can replay
    rng = random.Random(seed)

    tf = TeamFactory(log_level=levl, rng=rng)
    # Set up Home Team Record
    home_set = False
    if hasattr(args, "home"):
        if args.home:
            home_team_record = args.home
            home_set = True
    if not home_set:
        home_team_record = tf.generate_team(city=HOME_CITY, mascot=HOME_MASCOT)

    # Set up Away Team Record
    away_set = False
    if hasattr(args, "away"):
        if args.away:
            away_team_record = args.away
            away_set = True
    if not away_set:
        away_team_record = tf.generate_team(city=AWAY_CITY, mascot=AWAY_MASCOT)

    # setup TeamInGame objects
    home_team = TeamInGameFactory.from_record(home_team_record)
    away_team = TeamInGameFactory.from_record(away_team_record)

    # TODO we should find a better way to set bullpen roles.

    my_game = Game(
        home_team=home_team,
        away_team=away_team,
        logger=logger,
        pauses=args.pauses,
        rng=rng,
    )

    home_team.set_lineup()
    away_team.set_lineup()

    logger.info(home_team.output_lineup_ratings())
    logger.info(home_team.output_pitcher_ratings())
    logger.info(away_team.output_lineup_ratings())
    logger.info(away_team.output_pitcher_ratings())

    logger.info(home_team.output_lineup_skills())
    logger.info(home_team.output_pitcher_skills())
    logger.info(away_team.output_lineup_skills())
    logger.info(away_team.output_pitcher_skills())

    logger.info(home_team.output_lineup_card())
    logger.info(away_team.output_lineup_card())

    # logger.info(home_team.output_rotation_card())
    # logger.info(away_team.output_rotation_card())

    # logger.info(home_team.output_bullpen_card())
    # logger.info(away_team.output_bullpen_card())

    result = my_game.play()

    # Pitching decisions
    d = my_game.decisions
    if d:
        if d.win:
            logger.info(f"✅ Win:  {d.win.pitcher.name}")
        if d.loss:
            logger.info(f"❌ Loss: {d.loss.pitcher.name}")
        if d.save:
            logger.info(f"🔒 Save: {d.save.pitcher.name}")

    logger.info(home_team.output_defensive_stats())
    logger.info(away_team.output_defensive_stats())

    # logger.info(home_team.output_lineup_ratings())
    # logger.info(home_team.output_pitcher_ratings())
    # logger.info(away_team.output_lineup_ratings())
    # logger.info(away_team.output_pitcher_ratings())

    # logger.info(home_team.output_lineup_skills())
    # logger.info(home_team.output_pitcher_skills())
    # logger.info(away_team.output_lineup_skills())
    # logger.info(away_team.output_pitcher_skills())

    logger.info(home_team.output_batting_stats())
    logger.info(away_team.output_batting_stats())

    logger.info(home_team.output_pitching_stats())
    logger.info(away_team.output_pitching_stats())

    return result


if __name__ == "__main__":
    cli()
