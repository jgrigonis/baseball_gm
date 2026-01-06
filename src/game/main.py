import logging
import random

import src.game.bases as bases
import src.game.count as count
from src.game.defense.resolver import DefensiveResolver
import src.game.game_exceptions as game_exceptions
import src.game.inning as inning
from src.game.rules.common import pitch, batting_at_bat
import src.game.score as score
from src.game.score_formatter import ScoreFormatter
from src.game.stat_printer import output_stats
from src.util.logger import setup_logger

__author__ = "josh"
# TODO populate the other tables with info
# players - should populate this when we create a team
# also can be done one off
# teams - populate this when you create a team
# seasons - insert new record once a season
# series - insert new record once a series
# games - insert record for each game
# team_game_stats - insert record for each game
# pitcher_state - at least at the end of each game
# might update locally in Game. Also need to recover
# energy as "time" passes.
# plate_appearances - Can populated every plate appearance, someday
#
# TODO Fix up base advances, so they are not so static
# TODO verify defensive stats and event probs
# TODO defensive plays are very static.
# TODO pitchers probably should field bunts, and some batted balls
# TODO chance for dropped 3rd strike.
# TODO Steals, caught stealing, pickoffs all could result in errors
#      Make sure they are counted in fielding stats
# TODO implement handedness p vs batter
# TODO pitcher energy and recovery
# TODO implement clutch
# TODO Calculate W/L/S for pitchers
# TODO Track complete games, shutouts
# TODO We currently count all runs as earned.  Needs to be fixed.
# TODO Games Started for pitcher
# TODO can runners advance more with more speed, not currently
# TODO many more unit tests
# TODO unit test for walk off home run, vs driving in multiple
#      home run should score all runs, driving in on a triple for example
#      should stop scoring once the winning run crosses the plate.
# TODO handle intentional walk as a play and a stat
# TODO add a stat for catcher picking off runners.
# TODO add a stat for catcher having a passed ball.
# TODO can we get other types of double plays?
# Need to be line out double plays
# TODO the range of abilities is probably too low.
# TODO more accurately match stats from MLB teams
# TODO follow extra innings rules with runner on second.
# TODO In player replace rng.gauss with
# def generate_stat(self, rng, ...):
#    stat = rng.gauss(mean, sigma)
# TODO in player move the ratings into a RatingModel
# STRATEGY THINGS
# TODO Pitching changes
# TODO Mound visits
# TODO Pinch hitters
# TODO Pinch runners
# TODO Fielding Substitutions


class Game(object):
    """
    Maintain the state of the game.

    Includes methods to carry out various game
    related events.

    """

    def __init__(
        self, home, away, debug=logging.INFO, pauses=False, innings_per_game=9, rng=None
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
        self.pauses = pauses
        self.rng = rng or random.Random()
        self.count = count.Count()
        self.bases = bases.Bases()
        self.score = score.Score()
        self.winner = None
        self.game_over = False
        self.inning = inning.Inning()
        self.innings_per_game = innings_per_game
        self.logger = setup_logger(name="game", level=debug, console_level=debug)
        self.logger.game = self
        self.logger.debug("Game initialized")
        self.logger.info(self.inning)
        self.defense = DefensiveResolver(self.rng, self.logger)
        self._sync_players()
        self.init_game_stats()

    def init_game_stats(self):
        """
        This will clear out the current game stats for every player on both teams
        """
        for player in self.away.players + self.home.players:
            player.init_game_stats()

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
            self.logger.info({
                "event": "next_batter",
                "player": self.current_batter.name,
                #"player": self.current_batter,
                # "stats": f"AB: {self.current_batter.game_stats.batting.at_bats}"
            })
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

    def strike(self):
        """
        Pitcher throws a strike.

        If there are 2 strikes, call the _strike_out method.
        Otherwise, just increment the strike count.

        """
        pitch(self)
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
        pitch(self)
        if self.count.balls == 3:
            self._walk()
        else:
            self.count.ball()

    def foul_ball(self):
        """
        Batter hits a foul.

        If there are less than 2 strikes, increment the strike count.

        """
        pitch(self)
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
        pitch(self)
        batter.game_stats.batting.hit_batter()
        pitcher.game_stats.pitching.hit_batter()
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
        self.logger.trace("base to steal = " + str(b_num))
        if b_num == 3:
            if self.bases[2] != 0:
                self._score_run(self.bases[2])
                runner.game_stats.batting.steal()
                self.bases.clear(2)
                self.logger.info(f"{runner.name} stole home")
                return
        # If a steal is possible
        if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
            runner.game_stats.batting.steal()
            self.bases.advance(b_num - 1)
            # Log the steal with runner name
            base_names = {1: "second", 2: "third"}
            base_name = base_names.get(b_num, "base")
            self.logger.info(f"{runner.name} stole {base_name}")
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
                runner.game_stats.batting.caught_stealing()
                self.bases.clear([2])
                self._put_out(next=False, log="Runner caught stealing home")
            else:
                raise game_exceptions.InvalidSteal()
        elif b_num in [1, 2]:
            if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
                runner.game_stats.batting.caught_stealing()
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
            runner.game_stats.batting.pickoff()
            pitcher.game_stats.pitching.pickoff()

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
        pitch(self)

        # Determine which defender should field the ball
        if position is None:
            # Randomly pick an infield position (excluding pitcher)
            # pitchers probably should field bunts, and some batted balls
            infield_positions = ["ss", "2b", "3b", "1b"]
            position = random.choice(infield_positions)

        defender = self.get_defender(position)

        # Check if defender makes an error
        if defender:
            outcome = self.defense.check_play(defender, "fielding", position)
            if outcome.error:
                # self._handle_error(defender)
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
            elif outcome.slow:
                # self._handle_infield_hit()
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
                # Successful fielding - record assist and putout
                defender.game_stats.fielding.assist()
                defender.game_stats.fielding.putout()
                # Log the successful play
                self.logger.info(f"Ground out to {defender.name} at {position.upper()}")
        else:
            # No defender found at position - still log the out
            self.logger.info(f"Ground out to {position.upper()}")

        # Normal ground out - counts as at-bat
        batting_at_bat(batter)
        self._put_out(next=True, log="Normal ground out, batter out")

    def fly_out(self, position=None):
        """
        Batter flies out.

        :param position: Optional position where the ball is hit ('lf', 'cf', 'rf', etc.)
                         If None, randomly selects an outfield position.
        """
        self.logger.debug("Fly out")
        batter = self.current_batter
        pitch(self)

        # Determine which defender should catch the ball
        if position is None:
            # Randomly pick an outfield position
            outfield_positions = ["lf", "cf", "rf"]
            position = random.choice(outfield_positions)

        defender = self.get_defender(position)

        # Check if defender drops the ball (error)
        if defender:
            outcome = self.defense.check_play(defender, "fielding", position)
            if outcome.error:
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
            else:
                # Successful catch - record putout
                defender.game_stats.fielding.putout()
                # Log the successful play
                self.logger.info(f"Fly out to {defender.name} in {position.upper()}")
        else:
            # No defender found at position - still log the out
            self.logger.info(f"Fly out to {position.upper()}")

        # Normal fly out - counts as at-bat
        batting_at_bat(batter)
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
        self.current_pitcher.game_stats.pitching.balk()
        scorer = self.bases.advance_all()
        if scorer:
            self._score_run(scorer)

    def wild_pitch(self):
        """
        Call a ball, and also allow the runners to advance.
        """
        pitch(self)
        self.ball()
        if self.bases.men_on():
            self.current_pitcher.game_stats.pitching.wild_pitch()
            scorer = self.bases.advance_all()
            if scorer:
                self._score_run(scorer)

    def passed_ball(self):
        """
        Call a ball, and also allow the runners to advance.
        """
        pitch(self)
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
        pitch(self)
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
            batter.game_stats.batting.hit_rbi()
            if num == 4:
                self._score_run(scorer, score_all=True)
            else:
                self._score_run(scorer)
        if num == 4:
            batter.game_stats.batting.hit_rbi()
            batter.game_stats.batting.home_run()
            pitcher.game_stats.pitching.home_run()
            # We are done scoring the homer so set score_all to False
            self._score_run(batter, score_all=False)
        else:
            if num == 2:
                batter.game_stats.batting.double()
                pitcher.game_stats.pitching.double()
            elif num == 3:
                batter.game_stats.batting.triple()
                pitcher.game_stats.pitching.triple()
            self.bases[num - 1] = batter  # put the batter on base.
        batting_at_bat(batter)
        batter.game_stats.batting.hit()
        pitcher.game_stats.pitching.hit()
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
        pitch(self)
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
            # success, error_type = self.defense.check_play(
            #     first_defender, play_type="both", position=first_pos
            # )
            outcome = self.defense.check_play(first_defender, "both", first_pos)
            if outcome.error:
                # if error_type == "error":
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
            if outcome.slow:
                # elif error_type == "slow":
                # Too slow - only get lead runner, batter gets at-bat
                self.logger.info(
                    f"{first_defender.name} at {first_pos.upper()} too slow, only lead runner out"
                )
                batting_at_bat(batter)
                if gdp:
                    batter.game_stats.batting.ground_double_play()
                self.bases[b1] = 0
                self._put_out(next=True, log="Slow, double play failed")
                # Batter safe at first
                if self.bases.empty_base(0):
                    self.bases[0] = batter
                return
            else:
                # Successful first play - record assist
                first_defender.game_stats.fielding.assist()

        # Test second defender (1B) - check for error
        if first_baseman:
            outcome = self.defense.check_play(first_baseman, "fielding", position="1b")
            # success, error_type = self.defense.check_play(
            #     first_baseman, play_type="fielding", position="1b"
            # )

            # if not success and error_type == "error":
            if outcome.error:
                # Error on second defender - batter safe, no at-bat
                self.logger.info(f"Error by {first_baseman.name} at 1B")
                self.bases[b1] = 0
                self._put_out(next=True, log="Error")
                # Batter reaches on error
                if self.bases.empty_base(0):
                    self.bases[0] = batter
                return
            else:
                # Successful second play - record putout
                first_baseman.game_stats.fielding.putout()

        # Both plays successful - complete double play
        batting_at_bat(batter)
        if gdp:
            batter.game_stats.batting.ground_double_play()
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
        pitch(self)
        if self.bases.men_on() < 2:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs != 0:
            raise game_exceptions.TooManyOuts()
        batting_at_bat(batter)
        if gtp:
            batter.game_stats.batting.ground_triple_play()
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
        batting_at_bat(batter)
        pitch(self)
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
        pitch(self)
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
            batting_at_bat(batter)
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
        pitch(self)
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                batter.game_stats.batting.hit_rbi()
                self._score_run(scored)
        else:
            if isinstance(advances, tuple):
                advances = [advances]
            for adv in advances:
                if self.bases[adv[0]] == 0:
                    raise game_exceptions.NoRunnerToAdvance()
            scorers = self.bases.advance_many(advances)
            for scorer in scorers:
                batter.game_stats.batting.hit_rbi()
                self._score_run(scorer)
        batter.game_stats.batting.sac_fly()
        pitcher.game_stats.pitching.out()
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
        pitch(self)
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                batter.game_stats.batting.hit_rbi()
                self._score_run(scored)
        else:
            if isinstance(advances, tuple):
                advances = [advances]
            for adv in advances:
                if self.bases[adv[0]] == 0:
                    raise game_exceptions.NoRunnerToAdvance()
            scorers = self.bases.advance_many(advances)
            for scorer in scorers:
                batter.game_stats.batting.hit_rbi()
                self._score_run(scorer)
        batter.game_stats.batting.sac_bunt()
        pitcher.game_stats.pitching.out()
        self._next_batter(put_out=True, log="Sac bunt, batter is put out")
        self.inning.out()

    def _strike_out(self):
        """Batter strikes out."""
        batter = self.current_batter
        pitcher = self.current_pitcher

        batting_at_bat(batter)
        batter.game_stats.batting.strike_out()
        pitcher.game_stats.pitching.strike_out()

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
            batter.game_stats.batting.walk()
            pitcher.game_stats.pitching.walk()
        if self.bases[0] != 0:
            if self.bases[1] != 0:
                if self.bases[2] != 0:
                    self._score_run(self.bases[2])
                    batter.game_stats.batting.hit_rbi()
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
        self.logger.trace(f"{outs} outs")
        self.bat_team.next_batter()
        self.current_batter = self.bat_team.current_batter()
        self.count.reset_count()
        if not self.game_over and outs < 3:
            self.logger.info({
                "event": "next_batter",
                "player": self.current_batter.name,
                #"player": self.current_batter,
                # "stats": f"AB: {self.current_batter.game_stats.batting.at_bats}"
            })
            # self.logger.info(
            #     "Next Up: "
            #     + PlayerTableFormatter.short_batting_stats(self.current_batter)
            # )
            self.logger.debug(f"Pitching: {self.current_pitcher.name}")

    def _put_out(self, next=False, log=""):
        """Runner or batter is put out.

        :param next: if True, the batting order is incremented.
        :param log: if provided, the log message is logged.
        """
        self.logger.trace("Put out")
        if log:
            self.logger.trace(log)
        self.current_pitcher.game_stats.pitching.out()
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
        pitcher.game_stats.pitching.run()
        scorer.game_stats.batting.run(scorer)
        self.score.score_run()
        if self.inning.number >= self.innings_per_game:
            if not self.inning.top:
                if self.score.home > self.score.away:
                    self.logger.debug(
                        "_score_run in end of game, walk off scenario, END GAME"
                    )
                    self.logger.debug(
                        f"score_all was set to {score_all} and game_over was {self.game_over}"
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
        self.logger.debug(
            ScoreFormatter.inning_score_str(self.score, self.home, self.away)
        )
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
        self.logger.debug(
            ScoreFormatter.inning_score_str(self.score, self.home, self.away)
        )
        output_stats(self)
        return

    