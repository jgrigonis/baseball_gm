"""
Event generator.  The idea here is to return random events based
on the state of the game, including batter/pitcher abilities as
well as other pieces of information in the game state.

For instance, a steal will not occur with no one on base.  A triple
play won't happen with only 1 runner on, and so on.

"""
import random
from src.game.game_exceptions import GameException
__author__ = 'josh'


class Event(object):
    """Determine upcoming events based on game state."""
    def __init__(self, game, debug=False):
        """Use the game state found in game."""
        self.debug = debug
        self.game = game
        self.probs = None
        self.set_probs()
        self.event = None

    def __str__(self):
        """
        Just print the probs.  We print out the key, colon, one space
        then the value.  We right justify it so the whole string is just
        over 25 chars wide.

        """
        output = "\n"
        for key in self.probs.keys():
            output += str("{0}: {1:>{2}}").format(
                key,
                self.probs[key],
                25 - len(key))
            output += "\n"
        return output

    def do_event(self):
        """Generate one random event, and do it"""
        self.set_probs()
        self.event = self.random_event()
        self.handle_event()

        # TODO: handle_event needs to apply defensive filter

    def random_event(self):
        """
        Use a weighted probability.  probs is a dictionary of events
        and their probability as an integer.

        algorithm: sum up all the integer probabilities. Generate a
        random number between 0 and that sum. Step through the
        dictionary of probabilities subtracting its value from the
        random number until you get it lower than 0. This is guaranteed
        to happen.

        Whichever probability it ends on, return that event.

        """
        rand_num = random.random() * sum(self.probs.values())
        for index, value in enumerate(self.probs.values()):
            rand_num -= value
            if rand_num < 0:
                return list(self.probs)[index]
    
    def ball_or_strike(self):
        """
        In some cases we want a ball or strike to accompany another event
        such as a stolen base, or caught stealing.

        """
        ball = self.probs.get("ball")
        strike = self.probs.get("strike")
        rand_num = random.randint(0, ball + strike)
        if rand_num > ball:
            return "strike"
        else:
            return "ball"


    def handle_event(self):
        """
        Get and handle one event.

        We have try catch blocks around certain events so that they aren't
        invoked at the wrong time.

        """
        if self.event == 'ball':
            if self.game.count.balls == 3:
                self.display_text("Walk")
            else:
                self.display_text("  Ball {0}".format(self.game.count.balls + 1))
            self.game.ball()
        elif self.event == 'strike':
            if self.game.count.strikes == 2:
                self.display_text("Strike out")
            else:
                self.display_text("  Strike {0}".format(self.game.count.strikes + 1))
            self.game.strike()
        elif self.event == 'single':
            self.display_text("Single")
            self.game.hit(1)
        elif self.event == 'double':
            self.display_text("Double")
            self.game.hit(2)
        elif self.event == 'triple':
            self.display_text("Triple")
            self.game.hit(3)
        elif self.event == 'homer':
            self.display_text("Homer")
            self.game.hit(4)
        # TODO We need multiple cases of errors
        # errors should be able to move players anywhere, not just to first.
        elif self.event == 'error':
            try:
                # it's possible that first is occupied, and we'd get a
                # problem here.
                self.game.error(True)
                self.display_text("Error")
            except GameException:
                return None
        elif self.event == 'fly_out':
            self.display_text("Fly out")
            self.game.fly_out()
        elif self.event == 'ground_out':
            self.display_text("Ground out")
            self.game.ground_out()
        elif self.event == 'hit_by_pitch':
            self.display_text("Hit by pitch")
            self.game.hit_by_pitch()
        elif self.event == 'foul_ball':
            if self.game.count.strikes == 2:
                self.display_text("  Foul ball, still 2 strikes")
            else:
                self.display_text("  Foul ball, strike {0}".format(
                                        self.game.count.strikes + 1))
            self.game.foul_ball()
        elif self.event == 'balk':
            self.display_text("Balk")
            self.game.balk()
        elif self.event == 'sacrifice':
            if self.game.inning.outs != 2:
                self.display_text("Sacrifice")
                self.game.sacrifice()
            else:
                return None
        elif self.event == 'fielders_choice':
            try:
                # we only get fielders_choice if the runner was on first
                self.game.fielders_choice()
                self.display_text("Fielder's choice")
            except GameException:
                return None
        elif self.event == 'caught_stealing':
            try:
                # we only get caught_stealing if the runner was on first
                # and second is vacant
                self.game.caught_stealing("second")
                self.event = self.ball_or_strike()
                self.handle_event()
                self.display_text("Runner caught stealing second")
            except GameException:
                return None
        elif self.event == 'double_play':
            try:
                # we only get double_play if a runner was on first
                self.display_text("Double play")
                self.game.double_play()
            except GameException:
                return None
        elif self.event == 'picked_off':
            try:
                # we only get picked_off if a runner was on first
                self.display_text("Runner picked off first")
                self.game.picked_off("first")
            except GameException:
                return None
        # TODO should be able to steal third
        elif self.event == 'steal':
            try:
                # we only get steal if a runner was on first
                # and second is vacant
                self.game.steal("second")
                self.event = self.ball_or_strike()
                self.handle_event()
                self.display_text("Runner stole second")
            except GameException:
                return None
        elif self.event == 'triple_play':
            try:
                # we only get triple_play if at least 2 runners
                # are on base
                self.game.triple_play()
                self.display_text("Triple play")
            except GameException:
                return None
        elif self.event == 'wild_pitch':
            try:
                self.display_text("Wild Pitch, runners advance")
                self.game.wild_pitch()
            except GameException:
                return None
        elif self.event == 'passed_ball':
            try:
                self.display_text("Passed Ball, runners advance")
                self.game.passed_ball()
            except GameException:
                return None
        else:
            print(self.event)
            print("ERROR: We got a bad event.")
            quit()

    def display_text(self, text):
        """
        """
        if text != "" and self.debug:
            print(text)

    def set_probs(self):
        """
        Change the probs based on game state

        TODO: errors should be able to happen in concert with any play, 
            one example is extending a double to a three base hit with 
            the error.

        Pitching:
            'ACC': 0, # Accuracy (Reduces balls)
            'STA': 0, # Stamina (Nothing yet)
            'REC': 0, # Recovery speed with rest (Nothing yet)
            'CLU': 0, # Clutch (Nothing yet)

        """
        self.probs = {
            'ball': 10800,
            'strike': 7100,
            'foul_ball': 5100,
            'fly_out': 2050,
            'ground_out': 2050,
            'single': 1350,
            'double': 360,
            'homer': 280,
            'hit_by_pitch': 60,
            'triple': 45,
            'error': 10,
            'balk': 0,
            'caught_stealing': 0,
            'double_play': 0,
            'fielders_choice': 0,
            'picked_off': 0,
            'sacrifice': 0,
            'steal': 0,
            'triple_play': 0,
            'wild_pitch': 0,
            'passed_ball': 0,
        }
        # If a runner on first only
        if self.game.bases[0] != 0 and \
                self.game.bases[1] == 0 and \
                self.game.bases[2] == 0:
            self.set_probs_runner_on_first()
        # Runner on first and second only
        if self.game.bases[0] != 0 and \
                self.game.bases[1] != 0 and \
                self.game.bases[2] == 0:
            self.set_probs_runner_on_first_and_second()
        # Basees loaded
        if self.game.bases[0] != 0 and \
                self.game.bases[1] != 0 and \
                self.game.bases[2] == 0:
            self.set_probs_bases_loaded()
        # If a runner on second only
        if self.game.bases[0] == 0 and \
                self.game.bases[1] != 0 and \
                self.game.bases[2] == 0:
            self.set_probs_runner_on_second()
        # If a runner on third only
        if self.game.bases[0] == 0 and \
                self.game.bases[1] == 0 and \
                self.game.bases[2] != 0:
            self.set_probs_runner_on_third()
        # If a runner on second and third only
        if self.game.bases[0] == 0 and \
                self.game.bases[1] != 0 and \
                self.game.bases[2] != 0:
            self.set_probs_runner_on_second_and_third()
        if self.game.inning.outs == 2:
            self.set_probs_two_outs()
        elif self.game.inning.outs == 1:
            self.set_probs_one_out()
        # Count variation
        self.adjust_probs_based_on_count(
                self.game.count.balls, 
                self.game.count.strikes
            )
        # Men on base
        if self.game.bases[0] != 0 or \
                self.game.bases[1] != 0 or \
                self.game.bases[2] != 0:
            self.adjust_probs_men_on_base()
        #self.adjust_probs_batter()
        #self.adjust_probs_pitcher()
        # This is very noisy
        # if self.debug:
        #     print(self)


    def set_probs_runner_on_first(self):
        """
        Adjust probabilities for a single runner on first base.
        """
        self.probs['steal'] = 600
        self.probs['double_play'] = 400
        self.probs['caught_stealing'] = 200
        self.probs['balk'] = 10
        self.probs['fielders_choice'] = 100
        self.probs['picked_off'] = 50
        self.probs['sacrifice'] = 250
    
    def set_probs_runner_on_first_and_second(self):
        """
        Adjust probabilities for runners on first and second base.
        Third base empty.
        """
        self.probs['double_play'] = 400
        self.probs['triple_play'] = 40
        self.probs['balk'] = 10
        self.probs['fielders_choice'] = 100
        self.probs['picked_off'] = 20
        self.probs['sacrifice'] = 250 # TODO needs adjustment

    def set_probs_bases_loaded(self):
        """
        Adjust probabilities for bases loaded.
        """
        self.probs['double_play'] = 400
        self.probs['triple_play'] = 40
        self.probs['balk'] = 10

    def set_probs_runner_on_second(self):
        """
        Adjust probabilities for runner on second only.
        """
        self.probs['steal'] = 100 # TODO will steal work 2nd to third?
        self.probs['double_play'] = 100
        self.probs['balk'] = 10

    def set_probs_runner_on_third(self):
        """
        Adjust probabilities for runner on third only.
        """
        self.probs['steal'] = 10 # TODO will stealing home work?
        self.probs['double_play'] = 80
        self.probs['balk'] = 10

    def set_probs_runner_on_second_and_third(self):
        """
        Adjust probabilities for runner on second and third.
        """
        self.probs['steal'] = 10 # TODO will stealing home work?
        self.probs['double_play'] = 90
        self.probs['triple_play'] = 10
        self.probs['balk'] = 10
    
    def set_probs_one_out(self):
        """
        Adjust probabilities for 1 out.
        """
        self.probs['triple_play'] = 0
    def set_probs_two_outs(self):
        """
        Adjust probabilities for 2 outs.
        """
        self.probs['fielders_choice'] = 0
        self.probs['sacrifice'] = 0
        self.probs['double_play'] = 0
        self.probs['triple_play'] = 0

    def adjust_probs_men_on_base(self):
        """
        Adjust probabilities for any men on base at all.
        """
        self.probs['ball'] = int(self.probs['ball'] * 1.03)
        self.probs['strike'] = int(self.probs['strike'] * 0.97)
        self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.94)
        self.probs['single'] = int(self.probs['single'] * 1.18)
        self.probs['double'] = int(self.probs['double'] * 1.18)
        self.probs['triple'] = int(self.probs['triple'] * 1.18)
        self.probs['homer'] = int(self.probs['homer'] * 1.18)
        self.probs['wild_pitch'] = 100  # TODO adjust for pitcher accuracy
        self.probs['passed_ball'] = 100  # TODO adjust for catcher skill

    def adjust_probs_batter(self):
        """
        Adjust the probabilities based on the batter abilities
        """
        # power
        power = self.game.bat_team.current_batter().batting.skills['POW']
        self.probs['fly_out'] -= 4 * (power - 50)
        self.probs['homer'] = int(self.probs['homer'] * (power / 100.0))
        self.probs['single'] -= 1 * (power - 50)
        self.probs['double'] += 1 * (power - 50)
        # eye
        eye = self.game.bat_team.current_batter().batting.skills['EYE']
        self.probs['strike'] -= 8 * (eye - 50)
        self.probs['foul_ball'] += 4 * (eye - 50)
        self.probs['ball'] += 4 * (eye - 50)
        # contact
        contact = self.game.bat_team.current_batter().batting.skills['CON']
        self.probs['strike'] -= 4 * (contact - 50)
        self.probs['single'] += 2 * (contact - 50)
        self.probs['ground_out'] += 1 * (contact - 50)
        # speed
        speed = self.game.bat_team.current_batter().batting.skills['SPD']
        self.probs['ground_out'] -= (speed - 50)
        self.probs['single'] += .9 * (speed - 50)
        self.probs['double'] += .1 * (speed - 50)
        self.probs['triple'] += .1 * (speed - 50)
        if self.probs['double_play']:
            self.probs['double_play'] -= (speed - 50)
            self.probs['fielders_choice'] += (speed - 50)

    def adjust_probs_pitcher(self):
        """
        Adjust the probabilities based on the pitcher abilities
        """
        pass

    def adjust_probs_based_on_count(self, balls=0, strikes=0):
        """
        Adjust probabilities based on the count.
        """
        if balls == 0 and strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 1.15)
            self.probs['strike'] = int(self.probs['strike'] * 1.33)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.66)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.66)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.66)
            self.probs['single'] = int(self.probs['single'] * 0.61)
            self.probs['double'] = int(self.probs['double'] * 0.61)
            self.probs['triple'] = int(self.probs['triple'] * 0.61)
            self.probs['homer'] = int(self.probs['homer'] * 0.61)
        elif balls == 1 and strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 0.92)
            self.probs['strike'] = int(self.probs['strike'] * 1.12)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.94)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.01)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.01)
            self.probs['single'] = int(self.probs['single'] * 1.1)
            self.probs['double'] = int(self.probs['double'] * 1.1)
            self.probs['triple'] = int(self.probs['triple'] * 1.1)
            self.probs['homer'] = int(self.probs['homer'] * 1.1)
        elif balls == 0 and strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 1.13)
            self.probs['strike'] = int(self.probs['strike'] * 0.74)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.11)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.08)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.08)
            self.probs['single'] = int(self.probs['single'] * 0.78)
            self.probs['double'] = int(self.probs['double'] * 0.78)
            self.probs['triple'] = int(self.probs['triple'] * 0.78)
            self.probs['homer'] = int(self.probs['homer'] * 0.78)
        elif balls == 2 and strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 1.08)
            self.probs['strike'] = int(self.probs['strike'] * 1.44)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.57)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.72)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.72)
            self.probs['single'] = int(self.probs['single'] * 0.69)
            self.probs['double'] = int(self.probs['double'] * 0.69)
            self.probs['triple'] = int(self.probs['triple'] * 0.69)
            self.probs['homer'] = int(self.probs['homer'] * 0.69)
        elif balls == 1 and strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.96)
            self.probs['strike'] = int(self.probs['strike'] * 0.78)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.34)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.01)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.01)
            self.probs['single'] = int(self.probs['single'] * 1.15)
            self.probs['double'] = int(self.probs['double'] * 1.15)
            self.probs['triple'] = int(self.probs['triple'] * 1.15)
            self.probs['homer'] = int(self.probs['homer'] * 1.15)
        elif balls == 0 and strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 1.37)
            self.probs['strike'] = int(self.probs['strike'] * 0.6)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.02)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.82)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.82)
            self.probs['single'] = int(self.probs['single'] * 0.74)
            self.probs['double'] = int(self.probs['double'] * 0.74)
            self.probs['triple'] = int(self.probs['triple'] * 0.74)
            self.probs['homer'] = int(self.probs['homer'] * 0.74)
        elif balls == 3 and strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 0.89)
            self.probs['strike'] = int(self.probs['strike'] * 2.56)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.08)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.09)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.09)
            self.probs['single'] = int(self.probs['single'] * 0.21)
            self.probs['double'] = int(self.probs['double'] * 0.21)
            self.probs['triple'] = int(self.probs['triple'] * 0.21)
            self.probs['homer'] = int(self.probs['homer'] * 0.21)
        elif balls == 2 and strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.69)
            self.probs['strike'] = int(self.probs['strike'] * 0.89)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.19)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.47)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.47)
            self.probs['single'] = int(self.probs['single'] * 1.71)
            self.probs['double'] = int(self.probs['double'] * 1.71)
            self.probs['triple'] = int(self.probs['triple'] * 1.71)
            self.probs['homer'] = int(self.probs['homer'] * 1.71)
        elif balls == 1 and strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.97)
            self.probs['strike'] = int(self.probs['strike'] * 0.71)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.26)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.2)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.2)
            self.probs['single'] = int(self.probs['single'] * 1.16)
            self.probs['double'] = int(self.probs['double'] * 1.16)
            self.probs['triple'] = int(self.probs['triple'] * 1.16)
            self.probs['homer'] = int(self.probs['homer'] * 1.16)
        elif balls == 3 and strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.95)
            self.probs['strike'] = int(self.probs['strike'] * 0.76)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.79)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.56)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.56)
            self.probs['single'] = int(self.probs['single'] * 1.57)
            self.probs['double'] = int(self.probs['double'] * 1.57)
            self.probs['triple'] = int(self.probs['triple'] * 1.57)
            self.probs['homer'] = int(self.probs['homer'] * 1.57)
        elif balls == 2 and strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.65)
            self.probs['strike'] = int(self.probs['strike'] * 0.76)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.54)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.39)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.39)
            self.probs['single'] = int(self.probs['single'] * 1.63)
            self.probs['double'] = int(self.probs['double'] * 1.63)
            self.probs['triple'] = int(self.probs['triple'] * 1.63)
            self.probs['homer'] = int(self.probs['homer'] * 1.63)
        elif balls == 3 and strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.62)
            self.probs['strike'] = int(self.probs['strike'] * 0.65)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.36)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.88)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.88)
            self.probs['single'] = int(self.probs['single'] * 1.66)
            self.probs['double'] = int(self.probs['double'] * 1.66)
            self.probs['triple'] = int(self.probs['triple'] * 1.66)
            self.probs['homer'] = int(self.probs['homer'] * 1.66)
