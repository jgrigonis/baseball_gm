"""
Event generator.  The idea here is to return random events based
on the state of the game, including batter/pitcher abilities as
well as other pieces of information in the game state.

For instance, a steal will not occur with no one on base.  A triple
play won't happen with only 1 runner on, and so on.

"""
import random
__author__ = 'josh'


class Event(object):
    """Determine upcoming events based on game state."""
    def __init__(self, game):
        """Use the game state found in game."""
        self.probs = self.set_probs(game)

    def __str__(self):
        """Just print the probs.  We print out the key, colon, one space
        then the value.  We right justify it so the whole string is just
        over 25 chars wide.

        """
        output = "\n"
        for key in self.probs.keys():
            output += str("{0}: {1:>{2}}").format(key,
                                                  self.probs[key],
                                                  25 - len(key))
            output += "\n"
        return output

    def get_event(self):
        """Generate one random event."""
        return self.random_event(self.probs)

    @staticmethod
    def random_event(probs):
        """Use a weighted probability.  probs is a dictionary of events
        and their probability as an integer.
        :param probs: a dict of events as keys and probabilities as values
        """
        rand_num = random.random() * sum(probs.values())
        for index, offset in enumerate(probs.values()):
            rand_num -= offset
            if rand_num < 0:
                return list(probs)[index]

    def set_probs(self, my_game):
        """Change the probs based on game state

        :param my_game: is a game object and has the state of the game

        TODO: change state based on player skills

        TODO: errors can happen in concert with any play, one example is
            extending a double to a three base hit with the error.

        Pitching:
            # Nasty Factor should change per pitch, not per pitcher.
            'NF': 0, # Nasty Factor (Increases strikes, increases foul_ball)
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
        # If a runner on first
        # TODO adjust for base running skill and speed
        if my_game.bases[0] != 0 and \
                my_game.bases[1] == 0 and \
                my_game.bases[2] == 0:
            self.probs['steal'] = 600
            self.probs['double_play'] = 400
            self.probs['caught_stealing'] = 200
            self.probs['balk'] = 10
            self.probs['fielders_choice'] = 100
            self.probs['picked_off'] = 50
            self.probs['sacrifice'] = 250
        # Runner on first and second.  Non-specific on 3rd.
        if my_game.bases[0] != 0 and my_game.bases[1] != 0:
            self.probs['double_play'] = 400
            self.probs['triple_play'] = 40
            self.probs['balk'] = 10
        # TODO add case for runner on second and third base open
        # Count variation
        if my_game.count.balls == 0 and my_game.count.strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 1.15)
            self.probs['strike'] = int(self.probs['strike'] * 1.33)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.66)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.66)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.66)
            self.probs['single'] = int(self.probs['single'] * 0.61)
            self.probs['double'] = int(self.probs['double'] * 0.61)
            self.probs['triple'] = int(self.probs['triple'] * 0.61)
            self.probs['homer'] = int(self.probs['homer'] * 0.61)
        elif my_game.count.balls == 1 and my_game.count.strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 0.92)
            self.probs['strike'] = int(self.probs['strike'] * 1.12)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.94)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.01)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.01)
            self.probs['single'] = int(self.probs['single'] * 1.1)
            self.probs['double'] = int(self.probs['double'] * 1.1)
            self.probs['triple'] = int(self.probs['triple'] * 1.1)
            self.probs['homer'] = int(self.probs['homer'] * 1.1)
        elif my_game.count.balls == 0 and my_game.count.strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 1.13)
            self.probs['strike'] = int(self.probs['strike'] * 0.74)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.11)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.08)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.08)
            self.probs['single'] = int(self.probs['single'] * 0.78)
            self.probs['double'] = int(self.probs['double'] * 0.78)
            self.probs['triple'] = int(self.probs['triple'] * 0.78)
            self.probs['homer'] = int(self.probs['homer'] * 0.78)
        elif my_game.count.balls == 2 and my_game.count.strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 1.08)
            self.probs['strike'] = int(self.probs['strike'] * 1.44)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.57)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.72)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.72)
            self.probs['single'] = int(self.probs['single'] * 0.69)
            self.probs['double'] = int(self.probs['double'] * 0.69)
            self.probs['triple'] = int(self.probs['triple'] * 0.69)
            self.probs['homer'] = int(self.probs['homer'] * 0.69)
        elif my_game.count.balls == 1 and my_game.count.strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.96)
            self.probs['strike'] = int(self.probs['strike'] * 0.78)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.34)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.01)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.01)
            self.probs['single'] = int(self.probs['single'] * 1.15)
            self.probs['double'] = int(self.probs['double'] * 1.15)
            self.probs['triple'] = int(self.probs['triple'] * 1.15)
            self.probs['homer'] = int(self.probs['homer'] * 1.15)
        elif my_game.count.balls == 0 and my_game.count.strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 1.37)
            self.probs['strike'] = int(self.probs['strike'] * 0.6)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.02)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.82)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.82)
            self.probs['single'] = int(self.probs['single'] * 0.74)
            self.probs['double'] = int(self.probs['double'] * 0.74)
            self.probs['triple'] = int(self.probs['triple'] * 0.74)
            self.probs['homer'] = int(self.probs['homer'] * 0.74)
        elif my_game.count.balls == 3 and my_game.count.strikes == 0:
            self.probs['ball'] = int(self.probs['ball'] * 0.89)
            self.probs['strike'] = int(self.probs['strike'] * 2.56)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.08)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 0.09)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 0.09)
            self.probs['single'] = int(self.probs['single'] * 0.21)
            self.probs['double'] = int(self.probs['double'] * 0.21)
            self.probs['triple'] = int(self.probs['triple'] * 0.21)
            self.probs['homer'] = int(self.probs['homer'] * 0.21)
        elif my_game.count.balls == 2 and my_game.count.strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.69)
            self.probs['strike'] = int(self.probs['strike'] * 0.89)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.19)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.47)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.47)
            self.probs['single'] = int(self.probs['single'] * 1.71)
            self.probs['double'] = int(self.probs['double'] * 1.71)
            self.probs['triple'] = int(self.probs['triple'] * 1.71)
            self.probs['homer'] = int(self.probs['homer'] * 1.71)
        elif my_game.count.balls == 1 and my_game.count.strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.97)
            self.probs['strike'] = int(self.probs['strike'] * 0.71)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.26)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.2)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.2)
            self.probs['single'] = int(self.probs['single'] * 1.16)
            self.probs['double'] = int(self.probs['double'] * 1.16)
            self.probs['triple'] = int(self.probs['triple'] * 1.16)
            self.probs['homer'] = int(self.probs['homer'] * 1.16)
        elif my_game.count.balls == 3 and my_game.count.strikes == 1:
            self.probs['ball'] = int(self.probs['ball'] * 0.95)
            self.probs['strike'] = int(self.probs['strike'] * 0.76)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.79)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.56)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.56)
            self.probs['single'] = int(self.probs['single'] * 1.57)
            self.probs['double'] = int(self.probs['double'] * 1.57)
            self.probs['triple'] = int(self.probs['triple'] * 1.57)
            self.probs['homer'] = int(self.probs['homer'] * 1.57)
        elif my_game.count.balls == 2 and my_game.count.strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.65)
            self.probs['strike'] = int(self.probs['strike'] * 0.76)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.54)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.39)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.39)
            self.probs['single'] = int(self.probs['single'] * 1.63)
            self.probs['double'] = int(self.probs['double'] * 1.63)
            self.probs['triple'] = int(self.probs['triple'] * 1.63)
            self.probs['homer'] = int(self.probs['homer'] * 1.63)
        elif my_game.count.balls == 3 and my_game.count.strikes == 2:
            self.probs['ball'] = int(self.probs['ball'] * 0.62)
            self.probs['strike'] = int(self.probs['strike'] * 0.65)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 1.36)
            self.probs['fly_out'] = int(self.probs['fly_out'] * 1.88)
            self.probs['ground_out'] = int(self.probs['ground_out'] * 1.88)
            self.probs['single'] = int(self.probs['single'] * 1.66)
            self.probs['double'] = int(self.probs['double'] * 1.66)
            self.probs['triple'] = int(self.probs['triple'] * 1.66)
            self.probs['homer'] = int(self.probs['homer'] * 1.66)
        # Men on base
        if my_game.bases[0] != 0 or \
                my_game.bases[1] != 0 or \
                my_game.bases[2] != 0:
            self.probs['ball'] = int(self.probs['ball'] * 1.03)
            self.probs['strike'] = int(self.probs['strike'] * 0.97)
            self.probs['foul_ball'] = int(self.probs['foul_ball'] * 0.94)
            self.probs['single'] = int(self.probs['single'] * 1.18)
            self.probs['double'] = int(self.probs['double'] * 1.18)
            self.probs['triple'] = int(self.probs['triple'] * 1.18)
            self.probs['homer'] = int(self.probs['homer'] * 1.18)
            # self.probs['wild_pitch'] = 100  # TODO adjust for pitcher accuracy
            # self.probs['passed_ball'] = 100  # TODO adjust for catcher skill

        # power = my_game.bat_team.current_batter().batting.skills['POW']
        # self.probs['fly_out'] -= 4 * (power - 50)
        # self.probs['homer'] = int(self.probs['homer'] * (power / 100.0))
        # #  self.probs['homer'] += 4 * (power - 70)  # +120 to -280
        # self.probs['single'] -= 1 * (power - 50)
        # self.probs['double'] += 1 * (power - 50)
        # eye = my_game.bat_team.current_batter().batting.skills['EYE']
        # self.probs['strike'] -= 8 * (eye - 50)
        # self.probs['foul_ball'] += 4 * (eye - 50)
        # self.probs['ball'] += 4 * (eye - 50)
        # contact = my_game.bat_team.current_batter().batting.skills['CON']
        # self.probs['strike'] -= 4 * (contact - 50)
        # self.probs['single'] += 2 * (contact - 50)
        # self.probs['ground_out'] += 1 * (contact - 50)
        # speed = my_game.bat_team.current_batter().batting.skills['SPD']
        # self.probs['ground_out'] -= (speed - 50)
        # self.probs['single'] += .9 * (speed - 50)
        # self.probs['double'] += .1 * (speed - 50)
        # self.probs['triple'] += .1 * (speed - 50)
        # if self.probs['double_play']:
        #     self.probs['double_play'] -= (speed - 50)
        #     self.probs['fielders_choice'] += (speed - 50)

        return self.probs
