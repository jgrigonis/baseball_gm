import src.game.bases as bases
import src.game.count as count
import src.game.game_exceptions as game_exceptions
import src.game.inning as inning
import src.game.score as score
from src.stats import stats
__author__ = 'josh'


class Game(object):
    """
    Maintain the state of the game.

    Includes methods to carry out various game
    related events.

    At any given point we should know the count.
    The number of outs. The inning.

    TODO:
    The batter. The pitcher. The fielders.

    """
    def __init__(self, debug=False, pauses=False, innings_per_game=9):
        """Set up a new game.

        innings_per_game defaults to the number of innings in a
        standard game, it can be changed if you want to represent a
        little league game, or some type of exhibition game.

        """
        self.debug = debug
        self.pauses = pauses
        self.count = count.Count()
        self.bases = bases.Bases()
        self.stats = stats.Stats()
        self.score = score.Score()
        self.winner = None
        self.game_over = False
        self.inning = inning.Inning()
        self.innings_per_game = innings_per_game
        if debug:
            print(self.inning)
            print("------------")

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

        Call the stats.hbp method to update the stats.  Then call
        the _walk method with hbp set to True, so it knows not to
        also call the stats.walk method.  We don't want to track it
        as a walk, we just want to perform the same game functions.

        """
        self.stats.hbp()
        self._walk(hbp=True)

    def steal(self, base):
        """
        Runner steals a base.
        
        :param base: the base that is stolen (second, third, home)
        
        If the base to be stolen is not empty, or the base 
        they are stealing from is not occupied, an error is
        assumed to have occurred, and an exception will raise.
        
        """
        if base == "home":
            if self.bases[2] != 0:
                self._score_run(self.bases[2])
                self.stats.steal(self.bases[2])
                self.bases.clear(2) 
                return
        base_num = self._base_number(base)
        if self.bases[base_num - 1] != 0 and self.bases[base_num] == 0:
            self.stats.steal(self.bases[base_num - 1])
            self.bases.advance(base_num - 1)
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
        b_num = self._base_number(base)
        if b_num == "home" or b_num == 3:
            if self.bases[2] != 0:
                self.stats.caught_stealing(self.bases[2])
                self.bases.clear([2])
                self._put_out()
            else:
                raise game_exceptions.InvalidSteal()
        elif b_num in [0, 1, 2]:
            if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
                self.stats.caught_stealing(self.bases[b_num - 1])
                self.bases.clear([b_num - 1])
                self._put_out()
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
        base_number = self._base_number(base)
        if self.bases[base_number] != 0:
            self.bases.clear([0])
            self.stats.pick_off()
            self._put_out()
        else:
            raise game_exceptions.InvalidPickOff()
                
    def ground_out(self):
        """Batter grounds out."""
        self.stats.at_bat()
        self._next_batter()
        self._put_out()
        
    def fly_out(self):
        """Batter flies out."""
        self.stats.at_bat()
        self._next_batter()
        self._put_out()

    def balk(self):
        """
        Pitcher performs a balk.

        If no base runners are on, a balk has no effect.  If runners
        are on base, they will all be advanced one base, and possibly
        scored, if there is a runner on third.

        """
        if not self.bases.men_on():
            return
        scorer = self.bases.advance_all()
        if scorer:
            self._score_run(scorer)
    
    def wild_pitch(self):
        """
        Call a ball, and also allow the runners to advance.
        """
        self.ball()
        if self.bases.men_on():
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
        scorers = []
        if advances == "default":
            advances = []
            for abase in range(3):
                if not self.bases.empty_base(abase):
                    advances.append((abase, abase + num))
        if advances:
            if self.bases.men_on():
                scorers = self.bases.advance_many(advances)
        for scorer in scorers:
            self.stats.rbi()
            self._score_run(scorer)
        if num == 4:
            self.stats.rbi()
            self.stats.home_run()
            # TODO: This 1 should represent the batter
            self._score_run(1)
        else:
            if num == 2:
                self.stats.double()
            elif num == 3:
                self.stats.triple()
            # TODO: This 1 should represent the batter
            self.bases[num - 1] = 1  # put the batter on base.
        self.stats.at_bat()
        self.stats.hit()
        self._next_batter()

    def double_play(self, base1="second", base2="first", gdp=True):
        """
        Batter hits into a double play.
        
        :param base1: base where first out is made, assume force out.
        :param base2: base where second out is made.
        :param gdp: True if it was a grounder into a double.

        """
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.TooManyOuts()
        self.stats.at_bat()
        if gdp:
            self.stats.gdp()
        self._next_batter()
        self.bases[base1] = 0
        self._put_out()
        self.bases[base2] = 0
        self._put_out()

    def triple_play(self, gtp=True):
        """
        Batter hits into a triple play.

        :param gtp: should be set to True if it was a grounder into a triple
        play.

        """
        if self.bases.men_on() < 2:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs != 0:
            raise game_exceptions.TooManyOuts()
        self.stats.at_bat()
        if gtp:
            self.stats.gtp()
        # self.pitch_team_stats.out(3)
        # self.current_pitcher.out(3)
        self._next_batter()
        self._side_retired()

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
        self.stats.at_bat()
        self._next_batter()
        self.bases[base] = 0  # clear the base
        # TODO: first base needs to get the batter
        self._put_out()
    
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
            # TODO: This 1 should represent the batter
            self.bases[batter_base] = 1
            self.stats.at_bat()
            self._next_batter()
                            
    def sacrifice(self, advances=None):
        """
        Batter performs a sacrifice bunt or fly out.  By 
        default all base runners advance one base.  It wouldn't
        make sense to have a sacrifice and have no one advance.
        
        :param advances: is a list of tuples to advance runners from
        and to.
        
        """
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                self.stats.rbi()
                self._score_run(scored)
        else:
            if isinstance(advances, tuple):
                advances = [advances]
            for adv in advances:
                if self.bases[adv[0]] == 0:
                    raise game_exceptions.NoRunnerToAdvance()
            scorers = self.bases.advance_many(advances)
            for scorer in scorers:
                self.stats.rbi()
                self._score_run(scorer)
        self.stats.sacrifice()
        # self.pitch_team_stats.out()
        # self.current_pitcher.out()
        self.inning.out()
        self._next_batter()

    def _strike_out(self):
        """Batter strikes out."""
        self.stats.at_bat()
        self.stats.strike_out()
        self._next_batter()
        self._put_out()

    def _walk(self, hbp=False):
        """
        Walk the batter.

        If hbp is True, the batter was hit by pitch, so we don't
        call the stats.walk method.

        """
        if not hbp:
            self.stats.walk()
        if self.bases[0] != 0:
            if self.bases[1] != 0:
                if self.bases[2] != 0:
                    self._score_run(self.bases[2])
                    self.stats.rbi()
                else:
                    self.bases[2] = self.bases[1]
            else:
                self.bases[1] = self.bases[0]
        else:
            # TODO: This is just a 1, but should represent the actual batter
            self.bases[0] = 1
        self._next_batter()

    @staticmethod
    def _base_number(base):
        """Returns the base number, which is an index to the bases list."""
        if base == "first":
            return 0
        if base == "second":
            return 1
        if base == "third":
            return 2
        if base == "home":
            return 3
        return base
    
    def _next_batter(self):
        """Next batter is up in the lineup."""
        # self.bat_team.next_batter()
        # self.current_batter = \
        #     self.bat_team.current_batter().stats.batting
        self.count.reset_count()

    def _put_out(self):
        """Runner or batter is put out."""
        # self.current_pitcher.out()
        # self.pitch_team_stats.out()
        if self.inning.outs == 2:
            self._side_retired()
        else:
            self.inning.out()

    def _side_retired(self):
        """Three outs, time to switch sides, or end the game."""
        if self.inning.number >= self.innings_per_game:
            if self.inning.top:
                if self.score.home > self.score.away:
                    self._end_game()
            else:  # top
                if self.score.home != self.score.away:
                    self._end_game()
        self._new_inning()

    def _score_run(self, scorer):
        """
        Score a run.

        TODO: We currently count all runs as earned.  Needs to be fixed.
        TODO: We should add to the inning scores for home or away.

        """
        self.stats.run(scorer)
        self.score.score_run()
        # self.current_pitcher.earned_run()
        # self.pitch_team_stats.earned_run()
        # self.bat_team.score_run()
        if self.inning.number >= self.innings_per_game:
            if not self.inning.top:
                if self.score.home > self.score.away:
                    self._end_game()
        if self.debug:
            print(self.score)

    def _new_inning(self):
        """
        Start a fresh inning.

        Clear the bases, reset the count, change sides.

        TODO: Append to the inning scores list.  So we can track runs by
        inning.

        """
        self.score.new_inning()
        self.inning.increment()
        self.bases.clear()
        self.count.reset_count()
        if self.debug and not self.game_over:
            print(self.inning)
            print("------------")
        if self.pauses:
            input("")
        # if self.bat_team == self.away:
        #     self.bat_team = self.home
        #     self.pitch_team = self.away
        # else:
        #     self.bat_team = self.away
        #     self.pitch_team = self.home
        # self.bat_team_stats = self.bat_team.stats.batting
        # self.current_batter = self.bat_team.current_batter().stats.batting
        # self.pitch_team_stats = self.pitch_team.stats.pitching
        # self.current_pitcher = self.pitch_team.pitcher().stats.pitching

    def _end_game(self):
        """
        Game is over, winner is declared, unless tied.

        When would we ever have a tie?

        Apparently, this can happen even in MLB, and we
        may want to simulate other levels of play as well.

        """
        if self.score.home > self.score.away:
            self.winner = "home"
            # self.home.wins += 1
            # self.away.losses += 1
        elif self.score.away > self.score.home:
            self.winner = "away"
            # self.away.wins += 1
            # self.home.losses += 1
        else:
            # Tie
            self.winner = None
            # self.home.ties += 1
            # self.away.ties += 1
        self.game_over = True
        # self.home.save()
        # self.away.save()
        return
