import bases
import count
import inning
import stats
__author__ = 'josh'


class Game(object):
    """Maintain the state of the game.

    Includes methods to carry out various game
    related events.

    At any given point we should know the count.
    The number of outs. The inning.

    TODO:
    The score. The batter. The pitcher. The fielders.
    """
    def __init__(self, innings_per_game=9):
        """Set up a new game.

        innings_per_game defaults to the number of innings in a
        standard game, it can be changed if you want to represent a
        little league game, or some type of exhibition game.

        """
        self.count = count.Count()
        self.bases = bases.Bases()
        self.stats = stats.Stats()
        self.winner = None
        self.game_over = False
        self.innings = inning.Inning()
        self.innings_per_game = innings_per_game

    def strike(self):
        """Pitcher throws a strike.

        If there are 2 strikes, call the __strike_out method.
        Otherwise, just increment the strike count.

        """
        if self.count.strikes == 2:
            self._strike_out()
        else:
            self.count.strike()

    def _strike_out(self):
        """Batter strikes out."""
        # self.stats.atbat()
        # self.stats.strike_out()
        self._next_batter()
        self._put_out()

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
                if self.home.score > self.away.score:
                    self.end_game()
                    self._new_inning()
                    return
            else:  # top
                if self.home.score != self.away.score:
                    self.end_game()
                    self._new_inning()
                    return
        self.inning.increment()
        self._new_inning()

    def _new_inning(self):
        """Start a fresh inning.

        Clear the bases, reset the count, change sides.

        TODO: Append to the inning scores list.  So we can track runs by
        inning.

        """
        self.bases.clear()
        self.count.reset_count()
        self.inning.reset_outs()
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
