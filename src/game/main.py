import logging
import random

import src.game.bases as bases
import src.game.count as count
import src.game.game_exceptions as game_exceptions
import src.game.inning as inning
import src.game.score as score
from src.player.player import Player
from src.util.logger import setup_logger

__author__ = "josh"
# TODO verify defensive stats and event probs
# TODO implement handedness p vs batter
# TODO pitcher energy and recovery
# TODO track pitch counts
# TODO implement clutch
# TODO Calculate W/L/S for pitchers
# TODO Track complete games, shutouts
# TODO We currently count all runs as earned.  Needs to be fixed.
# TODO Games Started for pitcher
# TODO can runners advance more with more speed, not currently
# TODO many more unit tests
# TODO unit test for walk off home run, vs driving in multiple
# home run should score all runs, driving in on a triple for example
# should stop scoring once the winning run crosses the plate.
# TODO Append to the inning scores list.  So we can track runs by inning.
# TODO handle intentional walk as a play and a stat
# TODO add a stat for catcher picking off runners.
# TODO add a stat for catcher having a passed ball.
# TODO can we get other types of double plays?
# Need to be line out double plays
# TODO the range of abilities is probably too low.
# TODO more accurately match stats from MLB teams


class Game(object):
    """
    Maintain the state of the game.

    Includes methods to carry out various game
    related events.

    At any given point we should know the count.
    The number of outs. The inning.
    """

    def __init__(
        self, home, away, debug=False, pauses=False, innings_per_game=9, rng=None
    ):
        """Set up a new game.

        innings_per_game defaults to the number of innings in a
        standard game, it can be changed if you want to represent a
        little league game, or some type of exhibition game.

        """
        self.home = home
        self.away = away
        self.bat_team = away  # away bats first
        self.pitch_team = home
        if debug:
            levl = logging.DEBUG
        else:
            levl = logging.INFO
        levl = logging.TRACE  # uncomment this to see all the trace messages
        self.pauses = pauses
        self.rng = rng or random.Random()
        self.count = count.Count()
        self.bases = bases.Bases()
        self.score = score.Score()
        self.winner = None
        self.game_over = False
        self.inning = inning.Inning()
        self.innings_per_game = innings_per_game
        self.logger = setup_logger(name="game", level=levl)
        self.logger.game = self
        self.logger.debug("Game initialized")
        self.logger.info(self.inning)
        self._sync_players()

    def _format_outs(self):
        """Format the number of outs as a string."""
        outs = self.inning.outs
        if outs == 0:
            return "No outs."
        elif outs == 1:
            return "One out."
        else:
            return "Two outs."

    def _sync_players(self):
        """Sync the current batter and pitcher."""
        self.logger.debug("Syncing players")
        self.current_batter = self.bat_team.current_batter()
        self.current_pitcher = self.pitch_team.current_pitcher()
        if not self.game_over:
            self.logger.info("Next Up: " + self.current_batter.short_batting_stats())
            self.logger.info(f"Pitching: {self.current_pitcher.name}")

    def get_defender(self, position):
        """
        Get the defender at a specific position from the pitching team.

        :param position: The defensive position (e.g., 'ss', '2b', '1b', 'cf', etc.)
        :return: The Player object at that position, or None if not found
        """
        position = position.lower()
        for slot in self.pitch_team.lineup:
            if slot.position.lower() == position:
                return slot.player
        return None

    def check_defensive_play(self, defender, play_type="fielding", position=None):
        """
        TODO AI Slop here, fix it.
        Check if a defender successfully makes a defensive play.

        :param defender: The Player object making the play
        :param play_type: Type of play - 'fielding' (error chance), 'speed' (too slow), or 'both'
        :param position: Optional position being played (e.g., 'ss', 'cf', '1b').
                         If None, tries to determine from defender's position rating.
        :return: Tuple of (success, error_type)
            - success: True if play is successful, False if error or too slow
            - error_type: 'error' if fielding error, 'slow' if too slow, None if success
        """
        if defender is None:
            # No defender at position - assume error
            return (False, "error")

        # Determine which defensive skill to use based on position
        if position:
            pos = position.lower()
        else:
            # Try to determine from defender's best position rating
            # This is a fallback - ideally position should be passed
            pos = None

        # Base error rate depends on defensive skills
        # Use position-specific rating if available, otherwise use general skills
        if pos in ["c"]:
            defensive_skill = defender.skills.get("catching", 50)
        elif pos in ["1b", "2b", "3b", "ss"]:
            defensive_skill = defender.skills.get("infield", 50)
        elif pos in ["lf", "cf", "rf"]:
            defensive_skill = defender.skills.get("outfield", 50)
        else:
            # Fallback: use position rating if available, otherwise use infield skill
            if pos and pos in defender.ratings:
                # Use position rating as a proxy for skill
                defensive_skill = defender.ratings.get(pos, 50)
            else:
                # Default to infield skill
                defensive_skill = defender.skills.get("infield", 50)

        # Calculate error probability based on skill
        # Skill 100 = ~0.5% error rate, Skill 50 = ~5% error rate, Skill 0 = ~15% error rate
        base_error_rate = max(0.005, 0.15 - (defensive_skill / 100.0) * 0.145)

        # Add some randomness
        error_roll = self.rng.random()
        self.logger.debug(error_roll)

        if play_type in ["fielding", "both"]:
            if error_roll < base_error_rate:
                defender.stats.fielding.error()
                return (False, "error")

        # Check for being too slow (for double plays, etc.)
        if play_type in ["speed", "both"]:
            # Speed check - slower players more likely to be too slow
            speed = defender.skills.get("speed", 50)
            # Speed 100 = ~1% too slow, Speed 50 = ~5% too slow, Speed 0 = ~15% too slow
            slow_rate = max(0.01, 0.15 - (speed / 100.0) * 0.14)
            slow_roll = self.rng.random()

            if slow_roll < slow_rate:
                return (False, "slow")

        # Successful play
        return (True, None)

    def strike(self):
        """
        Pitcher throws a strike.

        If there are 2 strikes, call the _strike_out method.
        Otherwise, just increment the strike count.

        """
        if self.count.strikes == 2:
            self._strike_out()
        else:
            self.count.strike()

    def ball(self):
        """
        Pitcher throws a ball.

        If there are 3 balls, call the _walk method, otherwise
        just increment the ball count.

        """
        if self.count.balls == 3:
            self._walk()
        else:
            self.count.ball()

    def foul_ball(self):
        """
        Batter hits a foul.

        If there are less than 2 strikes, increment the strike count.

        """
        if self.count.strikes != 2:
            self.count.strike()

    def hit_by_pitch(self):
        """
        Batter is hit by pitch.

        Call the hit_batter method to update the stats.  Then call
        the _walk method with hbp set to True, so it knows not to
        also call the stats.batting.walk method.  We don't want to
        track it as a walk, we just want to perform the same game
        functions.

        """
        batter = self.current_batter
        pitcher = self.current_pitcher
        batter.stats.batting.hit_batter()
        pitcher.stats.pitching.hit_batter()
        self._walk(hbp=True)

    def steal(self, base):
        """
        Runner steals a base.

        :param base: the base that is stolen (second, third, home)

        If the base to be stolen is not empty, or the base
        they are stealing from is not occupied, an error is
        assumed to have occurred, and an exception will raise.

        """
        b_num = self._base_number(base)
        runner = self.bases[b_num - 1]
        self.logger.debug("base to steal = " + str(b_num))
        if b_num == 3:
            if self.bases[2] != 0:
                self._score_run(self.bases[2])
                runner.stats.batting.steal()
                self.bases.clear(2)
                self.logger.info("{} stole home".format(runner.name))
                return
        # If a steal is possible
        if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
            runner.stats.batting.steal()
            self.bases.advance(b_num - 1)
            # Log the steal with runner name
            base_names = {1: "second", 2: "third"}
            base_name = base_names.get(b_num, "base")
            self.logger.info("{} stole {}".format(runner.name, base_name))
            return
        raise game_exceptions.InvalidSteal()

    def caught_stealing(self, base):
        """
        Runner caught stealing a base.

        :param base: the base that is attempted to be stolen
        (second, third, home)

        If the base to be stolen is not empty, or the base
        they are stealing from is not occupied, an error is
        assumed to have occurred, and an exception will raise.

        """
        self.logger.debug("Caught stealing")
        b_num = self._base_number(base)
        runner = self.bases[b_num - 1]
        if b_num == 3:
            if self.bases[2] != 0:
                runner.stats.batting.caught_stealing()
                self.bases.clear([2])
                self._put_out(next=False, log="Runner caught stealing home")
            else:
                raise game_exceptions.InvalidSteal()
        elif b_num in [1, 2]:
            if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
                runner.stats.batting.caught_stealing()
                self.bases.clear([b_num - 1])
                self._put_out(next=False, log="Runner caught stealing from base")
            else:
                raise game_exceptions.InvalidSteal()
        else:
            raise game_exceptions.InvalidSteal()

    def picked_off(self, base):
        """
        Runner picked off from a base.

        :param base: the base that the runner was on
        (first, second, third) or (0, 1, 2)

        If base comes as a string, the _base_number function will
        translate it to an int.

        If the base is empty, an error is assumed to have occured,
        and an exception will raise.

        """
        b_num = self._base_number(base)
        runner = self.bases[b_num]
        pitcher = self.current_pitcher
        if self.bases[b_num] != 0:
            self.bases.clear([b_num])
            runner.stats.batting.pick_off()
            pitcher.stats.pitching.pick_off()

            self._put_out(next=False, log="Runner picked off from base")
        else:
            raise game_exceptions.InvalidPickOff()

    def ground_out(self, position=None):
        """
        TODO this needs some updating.
        Batter grounds out.

        :param position: Optional position where the ball is hit ('ss', '2b', '3b', '1b', etc.)
                         If None, randomly selects an infield position.
        """
        self.logger.debug("Ground out")
        batter = self.current_batter

        # Determine which defender should field the ball
        if position is None:
            # Randomly pick an infield position (excluding pitcher)
            infield_positions = ["ss", "2b", "3b", "1b"]
            position = random.choice(infield_positions)

        defender = self.get_defender(position)

        # Check if defender makes an error
        if defender:
            success, error_type = self.check_defensive_play(
                defender, play_type="fielding", position=position
            )
            if success:
                # Successful fielding - record assist and putout
                defender.stats.fielding.assist()
                defender.stats.fielding.putout()
                # Log the successful play
                self.logger.info(f"Ground out to {defender.name} at {position.upper()}")
            elif error_type == "error":
                # Batter reaches on error
                if self.bases.empty_base(0):
                    # Error on ground ball - batter safe, no at-bat
                    self.logger.info(f"Error by {defender.name} at {position.upper()}")
                    self.bases[0] = batter
                    self._next_batter(
                        put_out=False,
                        log="Ground out converted to error, batter reaches on error",
                    )
                else:
                    # TODO First base occupied - could advance runners or just record error
                    # For simplicity, just record error and batter is out
                    self._put_out(
                        next=True,
                        log="Ground out converted to error, but batter is out",
                    )
                return
            elif error_type == "slow":
                # Batter reaches on error
                if self.bases.empty_base(0):
                    # Error on ground ball - batter safe, no at-bat
                    self.logger.info(
                        f"Error by {defender.name} at {position.upper()}, he was too slow"
                    )
                    self.bases[0] = batter
                    self._next_batter(
                        put_out=False,
                        log="Ground out converted to error, batter reaches on error",
                    )
                else:
                    # First base occupied - could advance runners or just record error
                    # For simplicity, just record error and batter is out
                    self._put_out(
                        next=True,
                        log="Ground out converted to error, but batter is out",
                    )
                return

        else:
            # No defender found at position - still log the out
            self.logger.info(f"Ground out to {position.upper()}")

        # Normal ground out - counts as at-bat
        batter.stats.batting.at_bat()
        self._put_out(next=True, log="Normal ground out, batter out")

    def fly_out(self, position=None):
        """
        Batter flies out.

        :param position: Optional position where the ball is hit ('lf', 'cf', 'rf', etc.)
                         If None, randomly selects an outfield position.
        """
        self.logger.debug("Fly out")
        batter = self.current_batter

        # Determine which defender should catch the ball
        if position is None:
            # Randomly pick an outfield position
            outfield_positions = ["lf", "cf", "rf"]
            position = random.choice(outfield_positions)

        defender = self.get_defender(position)

        # Check if defender drops the ball (error)
        if defender:
            success, error_type = self.check_defensive_play(
                defender, play_type="fielding", position=position
            )

            if not success and error_type == "error":
                # Dropped fly ball - batter safe, no at-bat
                self.logger.info(
                    f"{defender.name} dropped the fly ball in {position.upper()}"
                )
                # Batter reaches on error
                if self.bases.empty_base(0):
                    self.bases[0] = batter
                    self._next_batter(
                        put_out=False,
                        log="Next batter: Fly out converted to error, batter reaches on error",
                    )
                else:
                    # First base occupied - could advance runners or just record error
                    # For simplicity, just record error and batter is out
                    self._put_out(
                        next=True, log="Fly out converted to error, batter out"
                    )
                return
            elif success:
                # Successful catch - record putout
                defender.stats.fielding.putout()
                # Log the successful play
                self.logger.info(f"Fly out to {defender.name} in {position.upper()}")
        else:
            # No defender found at position - still log the out
            self.logger.info(f"Fly out to {position.upper()}")

        # Normal fly out - counts as at-bat
        batter.stats.batting.at_bat()
        self._put_out(next=True, log="Normal fly out, batter out")

    def balk(self):
        """
        Pitcher performs a balk.

        If no base runners are on, a balk has no effect.  If runners
        are on base, they will all be advanced one base, and possibly
        scored, if there is a runner on third.

        """
        if not self.bases.men_on():
            return
        self.current_pitcher.stats.pitching.balk()
        scorer = self.bases.advance_all()
        if scorer:
            self._score_run(scorer)

    def wild_pitch(self):
        """
        Call a ball, and also allow the runners to advance.
        """
        self.ball()
        if self.bases.men_on():
            self.current_pitcher.stats.pitching.wild_pitch()
            scorer = self.bases.advance_all()
            if scorer:
                self._score_run(scorer)

    def passed_ball(self):
        """
        Call a ball, and also allow the runners to advance.
        """
        self.ball()
        if self.bases.men_on():
            scorer = self.bases.advance_all()
            if scorer:
                self._score_run(scorer)

    def hit(self, num=1, advances="default"):
        """
        Batter gets a base hit.

        :param num:
        1 = single
        2 = double
        3 = triple
        4 = home run

        By default, the hit is a single, and all runners advance
        one base.

        :param advances: are a list of tuples, there should be one
        tuple for each runner who advances on the play.  It
        should specify the from and to bases that the runner
        moved from and to.

        0 = first
        1 = second
        2 = third
        3+ = home

        In the case where the base runners didn't advance, advances
        should be passed in as None.

        """
        self.logger.debug("Hit")
        scorers = []
        to = 0
        batter = self.current_batter
        pitcher = self.current_pitcher
        if advances == "default":
            advances = []
            for abase in range(3):
                if not self.bases.empty_base(abase):
                    if abase + num > 3:
                        to = 3
                    else:
                        to = abase + num
                    advances.append((abase, to))
        if advances:
            if self.bases.men_on():
                scorers = self.bases.advance_many(advances)
        for scorer in scorers:
            batter.stats.batting.hit_rbi()
            if num == 4:
                self._score_run(scorer, score_all=True)
            else:
                self._score_run(scorer)
        if num == 4:
            batter.stats.batting.hit_rbi()
            batter.stats.batting.home_run()
            pitcher.stats.pitching.home_run()
            # We are done scoring the homer so set score_all to False
            self._score_run(batter, score_all=False)
        else:
            if num == 2:
                batter.stats.batting.double()
                pitcher.stats.pitching.double()
            elif num == 3:
                batter.stats.batting.triple()
                pitcher.stats.pitching.triple()
            self.bases[num - 1] = batter  # put the batter on base.
        batter.stats.batting.at_bat()
        batter.stats.batting.hit()
        pitcher.stats.pitching.hit()
        self._next_batter(put_out=False, log="Hit, batter reaches on hit")

    def double_play(self, base1="second", base2="first", gdp=True):
        """
        Batter hits into a double play.

        :param base1: base where first out is made, assume force out.
        :param base2: base where second out is made.
        :param gdp: True if it was a grounder into a double.

        """
        b1 = self._base_number(base1)
        b2 = self._base_number(base2)
        batter = self.current_batter
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.TooManyOuts()

        # Determine which defenders are involved based on bases
        # Common double play: 6-4-3 (SS to 2B to 1B)
        # Or 4-6-3 (2B to SS to 1B)
        # For simplicity, we'll test SS, 2B, and 1B in sequence
        ss = self.get_defender("ss")
        second_baseman = self.get_defender("2b")
        first_baseman = self.get_defender("1b")

        # Determine who fields the ball at second base (SS or 2B)
        # Randomly pick based on who's available, or prefer SS for 6-4-3
        first_defender = None
        first_pos = None
        if ss and second_baseman:
            # Randomly pick SS or 2B to field it
            if random.random() < 0.6:  # 60% chance SS fields it (6-4-3)
                first_defender = ss
                first_pos = "ss"
            else:  # 40% chance 2B fields it (4-6-3)
                first_defender = second_baseman
                first_pos = "2b"
        elif ss:
            first_defender = ss
            first_pos = "ss"
        elif second_baseman:
            first_defender = second_baseman
            first_pos = "2b"

        # Test first defender (SS or 2B) - check for error or being too slow
        if first_defender:
            success, error_type = self.check_defensive_play(
                first_defender, play_type="both", position=first_pos
            )

            if not success:
                if error_type == "error":
                    # Error on first defender - batter safe, runner out, no at-bat
                    self.logger.info(
                        f"Error by {first_defender.name} at {first_pos.upper()}"
                    )
                    self.bases[b1] = 0
                    self._put_out(next=True, log="Error, double play failed")
                    # Batter reaches on error
                    if self.bases.empty_base(0):
                        self.bases[0] = batter
                    return
                elif error_type == "slow":
                    # Too slow - only get lead runner, batter gets at-bat
                    self.logger.info(
                        f"{first_defender.name} at {first_pos.upper()} too slow, only lead runner out"
                    )
                    batter.stats.batting.at_bat()
                    if gdp:
                        batter.stats.batting.ground_double_play()
                    self.bases[b1] = 0
                    self._put_out(next=True, log="Slow, double play failed")
                    # Batter safe at first
                    if self.bases.empty_base(0):
                        self.bases[0] = batter
                    return
            else:
                # Successful first play - record assist
                first_defender.stats.fielding.assist()

        # Test second defender (1B) - check for error
        if first_baseman:
            success, error_type = self.check_defensive_play(
                first_baseman, play_type="fielding", position="1b"
            )

            if not success and error_type == "error":
                # Error on second defender - batter safe, no at-bat
                self.logger.info(f"Error by {first_baseman.name} at 1B")
                self.bases[b1] = 0
                self._put_out(next=True, log="Error")
                # Batter reaches on error
                if self.bases.empty_base(0):
                    self.bases[0] = batter
                return
            elif success:
                # Successful second play - record putout
                first_baseman.stats.fielding.putout()

        # Both plays successful - complete double play
        batter.stats.batting.at_bat()
        if gdp:
            batter.stats.batting.ground_double_play()
        self.bases[b1] = 0
        self._put_out(next=False, log="Double play first out")
        self.bases[b2] = 0
        self._put_out(next=True, log="Double play")

    def triple_play(self, gtp=True):
        """
        Batter hits into a triple play.

        :param gtp: should be set to True if it was a grounder into a triple
        play.

        """
        batter = self.current_batter
        if self.bases.men_on() < 2:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs != 0:
            raise game_exceptions.TooManyOuts()
        batter.stats.batting.at_bat()
        if gtp:
            batter.stats.batting.ground_triple_play()
        self._put_out(next=False, log="Triple play first out")
        self._put_out(next=False, log="Triple play second out")
        self._put_out(next=True, log="Triple play")

    def fielders_choice(self, base="second"):
        """
        Batter hits into a fielder's choice.

        A fielder's choice is when a runner is on base, the
        batter hits the ball such that the runner is put out,
        but the batter is then able to get on base.

        :param base: base where the out is made, assume force out.
        It defaults to second, as that is the most common fielder's
        choice.

        """
        b_num = self._base_number(base)
        batter = self.current_batter
        batter.stats.batting.at_bat()
        self._next_batter(
            put_out=True, log="Fielder's choice, batter reaches on fielder's choice"
        )
        self.bases[b_num] = 0  # clear the base
        self.bases[0] = batter
        self._put_out(next=True, log="Fielder's choice")

    def error(self, batter_on_base=False, advances=None):
        """
        Fielder makes an error.  By default nothing happens
        other than to take note of the error.

        :param batter_on_base: determines if the batter got on base during
        this error.  If True, the batter will occupy first base.

        If the batter were to get multiple bases, the batter_on_base can
        be set to 1 for "second", 2 for "third", and in some really weird
        circumstances, 3 for "home" for an error based home run.

        :param advances: is a list of tuples to advance runners from and to.

        """
        self.logger.debug("Error")
        batter = self.current_batter
        scorers = []
        if advances:
            if self.bases.men_on():
                scorers = self.bases.advance_many(advances)
            else:
                raise game_exceptions.NoRunnerToAdvance()
        for scorer in scorers:
            self._score_run(scorer)
        if batter_on_base:
            if batter_on_base is True:
                batter_base = 0
            else:
                batter_base = self._base_number(batter_on_base)
            if not self.bases.empty_base(batter_base):
                raise game_exceptions.InvalidAdvance()
            self.bases[batter_base] = batter
            batter.stats.batting.at_bat()
            self._next_batter(log="Error")

    def sac_fly(self, advances=None):
        """
        Batter performs a sac_fly fly out.  By
        default all base runners advance one base.  It wouldn't
        make sense to have a sac_fly and have no one advance.

        :param advances: is a list of tuples to advance runners from
        and to.

        """
        batter = self.current_batter
        pitcher = self.current_pitcher
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                batter.stats.batting.hit_rbi()
                self._score_run(scored)
        else:
            if isinstance(advances, tuple):
                advances = [advances]
            for adv in advances:
                if self.bases[adv[0]] == 0:
                    raise game_exceptions.NoRunnerToAdvance()
            scorers = self.bases.advance_many(advances)
            for scorer in scorers:
                batter.stats.batting.hit_rbi()
                self._score_run(scorer)
        batter.stats.batting.sac_fly()
        pitcher.stats.pitching.out()
        self._next_batter(put_out=True, log="Sac fly, batter is put out")
        self.inning.out()

    def sac_bunt(self, advances=None):
        """
        Batter performs a sac_bunt bunt.  By
        default all base runners advance one base.  It wouldn't
        make sense to have a sac_bunt and have no one advance.
        """
        batter = self.current_batter
        pitcher = self.current_pitcher
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                batter.stats.batting.hit_rbi()
                self._score_run(scored)
        else:
            if isinstance(advances, tuple):
                advances = [advances]
            for adv in advances:
                if self.bases[adv[0]] == 0:
                    raise game_exceptions.NoRunnerToAdvance()
            scorers = self.bases.advance_many(advances)
            for scorer in scorers:
                batter.stats.batting.hit_rbi()
                self._score_run(scorer)
        batter.stats.batting.sac_bunt()
        pitcher.stats.pitching.out()
        self._next_batter(put_out=True, log="Sac bunt, batter is put out")
        self.inning.out()

    def _strike_out(self):
        """Batter strikes out."""
        batter = self.current_batter
        pitcher = self.current_pitcher

        batter.stats.batting.at_bat()
        batter.stats.batting.strike_out()
        pitcher.stats.pitching.strike_out()

        self._put_out(next=True, log="Strike Out")

    def _walk(self, hbp=False):
        """
        Walk the batter.

        If hbp is True, the batter was hit by pitch, so we don't
        call the stats.walk method.

        """
        batter = self.current_batter
        pitcher = self.current_pitcher
        if not hbp:
            batter.stats.batting.walk()
            pitcher.stats.pitching.walk()
        if self.bases[0] != 0:
            if self.bases[1] != 0:
                if self.bases[2] != 0:
                    self._score_run(self.bases[2])
                    batter.stats.batting.hit_rbi()
                else:
                    self.bases[2] = self.bases[1]
            else:
                self.bases[1] = self.bases[0]
        else:
            self.bases[0] = batter
        self._next_batter(log="Walk, batter reaches on walk")

    @staticmethod
    def _base_number(base):
        """Returns the base number, which is an index to the bases list."""
        mapping = {
            "first": 0,
            "second": 1,
            "third": 2,
            "home": 3,
        }
        if isinstance(base, str):
            if base not in mapping:
                raise game_exceptions.InvalidBase(f"Invalid base: {base}")
            return mapping[base]
        if isinstance(base, int) and 0 <= base <= 3:
            return base
        raise game_exceptions.InvalidBase(f"Invalid base: {base}")

    def _next_batter(self, put_out=False, log=""):
        """Increment the batting order and set the current batter."""
        self.logger.debug("Next batter in lineup")
        self.logger.trace(log)
        outs = self.inning.outs
        if put_out:
            outs += 1
        self.logger.trace("{} outs".format(outs))
        self.bat_team.next_batter()
        self.current_batter = self.bat_team.current_batter()
        self.count.reset_count()
        if not self.game_over and outs < 3:
            self.logger.info("Next Up: " + self.current_batter.short_batting_stats())
            self.logger.debug(f"Pitching: {self.current_pitcher.name}")

    def _put_out(self, next=False, log=""):
        """Runner or batter is put out.

        :param next: if True, the batting order is incremented.
        :param log: if provided, the log message is logged.
        """
        self.logger.trace("Put out")
        if log:
            self.logger.trace(log)
        self.current_pitcher.stats.pitching.out()
        if next:
            self._next_batter(put_out=True, log="put out, next batter")
        was_two_outs = self.inning.outs == 2
        if was_two_outs:
            # This was the third out - side is retired
            self._side_retired()
        else:
            self.inning.out()  # Increment the outs
        if next and self.game_over is False:
            self.logger.info(f"Bases: {self.bases} {self._format_outs()}")

    def _side_retired(self):
        """Three outs, time to switch sides, or end the game."""
        self.logger.debug("Side retired")
        if self.inning.number >= self.innings_per_game:
            if self.inning.top:
                if self.score.home > self.score.away:
                    self.logger.debug(
                        "Side retired in top of inning home in lead, END GAME"
                    )
                    self._end_game()
            else:  # top
                if self.score.home != self.score.away:
                    self.logger.debug(
                        "Side retired in bottom of inning, scores differ, END GAME"
                    )
                    self._end_game()
        if not self.game_over:
            self.logger.info("Side Retired")
            self._new_inning()

    def _score_run(self, scorer, score_all=False):
        """
        Score a run.
        """
        if self.game_over and not score_all:
            return
        pitcher = self.current_pitcher
        pitcher.stats.pitching.run()
        scorer.stats.batting.run(scorer)
        self.score.score_run()
        if self.inning.number >= self.innings_per_game:
            if not self.inning.top:
                if self.score.home > self.score.away:
                    self.logger.debug(
                        "_score_run in end of game, walk off scenario, END GAME"
                    )
                    self.logger.debug(
                        "score_all was set to {} and game_over was {}".format(
                            score_all, self.game_over
                        )
                    )
                    if not score_all:
                        self._end_game()
        self.logger.info(self.score)

    def _new_inning(self):
        """
        Start a fresh inning.

        Clear the bases, reset the count, change sides.

        """
        self.logger.debug("New inning")
        self.score.new_inning()
        self.inning.increment()
        self.bases.clear()
        self.count.reset_count()
        if not self.game_over:
            # Log the inning
            self.logger.info(self.inning)
        if self.pauses:
            input("Press enter to continue")
        if self.bat_team == self.away:
            self.bat_team = self.home
            self.pitch_team = self.away
        else:
            self.bat_team = self.away
            self.pitch_team = self.home
        self._sync_players()

    def _aggregate_stats(self):
        self.logger.debug("Aggregating game stats to season total.")
        for player in self.home.players:
            player.aggregate_game()
        for player in self.away.players:
            player.aggregate_game()

    def _end_game(self):
        """
        Game is over, winner is declared, unless tied.

        When would we ever have a tie?

        Apparently, this can happen even in MLB, and we
        may want to simulate other levels of play as well.

        """
        if self.score.home > self.score.away:
            self.winner = self.home
            # self.home.wins += 1
            # self.away.losses += 1
        elif self.score.away > self.score.home:
            self.winner = self.away
            # self.away.wins += 1
            # self.home.losses += 1
        else:
            # Tie
            self.winner = None
            # self.home.ties += 1
            # self.away.ties += 1
        self.game_over = True
        self.logger.info("Game Over")
        self._handle_stats()
        return

    def _handle_stats(self):
        """Handle the stats for the game."""
        self.logger.info(
            Player.horizontal_stat_header(self.home.city + " " + self.home.mascot)
        )
        for player in self.home.lineup:
            self.logger.info(player.horizontal_stats())

        self.logger.info(
            Player.horizontal_stat_header(self.away.city + " " + self.away.mascot)
        )
        for player in self.away.lineup:
            self.logger.info(player.horizontal_stats())
        self.logger.info("-" * 100)
        self.logger.info(
            Player.horizontal_pitching_stat_header(
                self.home.city + " " + self.home.mascot
            )
        )
        for player in self.home.players:
            if player.stats.pitching.ip_float > 0:
                self.logger.info(player.horizontal_pitching_stats())

        self.logger.info(
            Player.horizontal_pitching_stat_header(
                self.away.city + " " + self.away.mascot
            )
        )
        for player in self.away.players:
            if player.stats.pitching.ip_float > 0:
                self.logger.info(player.horizontal_pitching_stats())
        self.logger.info("-" * 100)
        self._aggregate_stats()
