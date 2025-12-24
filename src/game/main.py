import src.game.bases as bases
import src.game.count as count
import src.game.game_exceptions as game_exceptions
import src.game.inning as inning
import src.game.score as score
from src.team.team import Team
# from src.stats import stats
__author__ = 'josh'


class Game(object):
    """
    Maintain the state of the game.

    Includes methods to carry out various game
    related events.

    At any given point we should know the count.
    The number of outs. The inning.

    TODO:
    The lineups for both teams.

    """
    def __init__(self, home, away, debug=False, pauses=False, innings_per_game=9):
        """Set up a new game.

        innings_per_game defaults to the number of innings in a
        standard game, it can be changed if you want to represent a
        little league game, or some type of exhibition game.

        """
        self.home = home
        self.away = away
        self.bat_team = away     # away bats first
        self.pitch_team = home
        self.debug = debug
        self.pauses = pauses
        self.count = count.Count()
        self.bases = bases.Bases()
        #self.stats = stats.Stats()
        self.score = score.Score()
        self.winner = None
        self.game_over = False
        self.inning = inning.Inning()
        self.innings_per_game = innings_per_game

        self._sync_players()

        if debug:
            print(self.inning)
            print("------------")
            print(self.current_batter)
            print(self.current_pitcher)

    def _sync_players(self):
        self.current_batter = self.bat_team.current_batter()
        self.current_pitcher = self.pitch_team.current_pitcher()

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
        #pitcher = self.current_pitcher
        if self.debug:
            print("base to steal = " + str(b_num))
        if b_num == 3:
            if self.bases[2] != 0:
                self._score_run(self.bases[2])
                #self.stats.steal(self.bases[2])
                runner.stats.batting.steal()
                self.bases.clear(2) 
                return
        # If a steal is possible
        if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
            runner.stats.batting.steal()
            #self.stats.steal(self.bases[b_num - 1])
            self.bases.advance(b_num - 1)
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
        # TODO add a stat for catchers
        b_num = self._base_number(base)
        runner = self.bases[b_num - 1]
        if b_num == 3:
            if self.bases[2] != 0:
                runner.stats.batting.caught_stealing()
                #self.stats.caught_stealing(self.bases[2])
                self.bases.clear([2])
                self._put_out()
            else:
                raise game_exceptions.InvalidSteal()
        elif b_num in [1, 2]:
            if self.bases[b_num - 1] != 0 and self.bases[b_num] == 0:
                runner.stats.batting.caught_stealing()
                #self.stats.caught_stealing(self.bases[b_num - 1])
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
        # TODO add a stat for pitcher
        b_num = self._base_number(base)
        runner = self.bases[b_num]
        pitcher = self.current_pitcher
        if self.bases[b_num] != 0:
            self.bases.clear([b_num])
            #self.stats.pick_off()
            runner.stats.batting.pick_off()

            self._put_out()
        else:
            raise game_exceptions.InvalidPickOff()
                
    def ground_out(self):
        """Batter grounds out."""
        self.current_batter.stats.batting.at_bat()
        self._next_batter()
        self._put_out()
        
    def fly_out(self):
        """Batter flies out."""
        self.current_batter.stats.batting.at_bat()
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
        to = 0
        batter = self.current_batter
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
            #self.stats.rbi()
            batter.stats.batting.hit_rbi()
            self._score_run(scorer)
        if num == 4:
            #self.stats.rbi()
            batter.stats.batting.hit_rbi()
            #self.stats.home_run()
            batter.stats.batting.home_run()
            self._score_run(batter)
        else:
            if num == 2:
                #self.stats.double()
                batter.stats.batting.double()
            elif num == 3:
                #self.stats.triple()
                batter.stats.batting.triple()
            self.bases[num - 1] = batter  # put the batter on base.
        #self.stats.at_bat()
        batter.stats.batting.at_bat()
        #self.stats.hit()
        batter.stats.batting.hit()
        self._next_batter()
        if self.debug:
            print("DEBUG:")
            print("1st base has " + str(self.bases[0]))

    def double_play(self, base1="second", base2="first", gdp=True):
        """
        Batter hits into a double play.
        
        :param base1: base where first out is made, assume force out.
        :param base2: base where second out is made.
        :param gdp: True if it was a grounder into a double.

        #TODO can we get other types of double plays?
        # Need to be line out double plays

        """
        b1 = self._base_number(base1)
        b2 = self._base_number(base2)
        batter = self.current_batter
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.TooManyOuts()
        #self.stats.at_bat()
        batter.stats.batting.at_bat()
        if gdp:
            batter.stats.batting.ground_double_play()
            #self.stats.gdp()
        self._next_batter()
        self.bases[b1] = 0
        self._put_out()
        self.bases[b2] = 0
        self._put_out()

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
        #self.stats.at_bat()
        batter.stats.batting.at_bat()
        if gtp:
            #self.stats.gtp()
            batter.stats.batting.ground_triple_play()
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
        b_num = self._base_number(base)
        batter = self.current_batter
        #self.stats.at_bat()
        batter.stats.batting.at_bat()
        self._next_batter()
        self.bases[b_num] = 0  # clear the base
        self.bases[0] = batter
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
            #self.stats.at_bat()
            self._next_batter()
                            
    def sacrifice(self, advances=None):
        """
        Batter performs a sacrifice bunt or fly out.  By 
        default all base runners advance one base.  It wouldn't
        make sense to have a sacrifice and have no one advance.
        
        :param advances: is a list of tuples to advance runners from
        and to.
        
        """
        batter = self.current_batter
        if self.bases.men_on() == 0:
            raise game_exceptions.NotEnoughRunnersOnBase()
        if self.inning.outs == 2:
            raise game_exceptions.BadSacrifice()
        if not advances:
            scored = self.bases.advance_all()
            if scored:
                batter.stats.batting.hit_rbi()
                #self.stats.rbi()
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
                #self.stats.rbi()
                self._score_run(scorer)
        batter.stats.batting.sacrifice()        
        #self.stats.sacrifice()
        # self.pitch_team_stats.out()
        # self.current_pitcher.out()
        self.inning.out()
        self._next_batter()

    def _strike_out(self):
        """Batter strikes out."""
        batter = self.current_batter
        pitcher = self.current_pitcher

        batter.stats.batting.at_bat()
        batter.stats.batting.strike_out()
        pitcher.stats.pitching.strike_out()

        self._next_batter()
        self._put_out()

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
            #self.stats.walk()
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
        self._next_batter()

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
    
    def _next_batter(self):
        """Next batter is up in the lineup."""
        if self.debug:
            print(self.current_batter.horizontal())
        self.bat_team.next_batter()
        self.current_batter = self.bat_team.current_batter()
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
        # need to update this
#        self.stats.run(scorer)
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
        # if self.debug:
        #     self.current_batter.rate_player()
        #     print(self.current_batter.horizontal())
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
        # if self.debug:
        #     print(self.current_batter.first_name)
        #     print(self.current_batter.stats.batting.rbi)
        return
