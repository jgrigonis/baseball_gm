# src/game/score.py
class Score:
    def __init__(self):
        self.away_innings = []
        self.home_innings = []

    def __str__(self):
        """Return the score as a string."""
        output = "\n"
        output += "Home:    " + str(self.home) + "\n"
        output += "Visitor: " + str(self.away) + "\n"
        return output

    def ensure_inning(self, inning_number: int):
        while len(self.away_innings) < inning_number:
            self.away_innings.append(0)
        while len(self.home_innings) < inning_number:
            self.home_innings.append(0)

    def score_run(self, *, top: bool, inning_number: int):
        self.ensure_inning(inning_number)
        if top:
            self.away_innings[inning_number - 1] += 1
        else:
            self.home_innings[inning_number - 1] += 1

    @property
    def away(self):
        return sum(self.away_innings)

    @property
    def home(self):
        return sum(self.home_innings)


# # src/game/score.py
# class Score(object):
#     """Keep track of the score."""

#     def __init__(self):
#         self.away_innings = [0]
#         self.home_innings = []

# def __str__(self):
#     """Return the score as a string."""
#     output = "\n"
#     output += "Home:    " + str(self.home) + "\n"
#     output += "Visitor: " + str(self.away) + "\n"
#     return output

#     @property
#     def away(self):
#         """Return the away score."""
#         return sum(self.away_innings)

#     @property
#     def home(self):
#         """Return the home score."""
#         return sum(self.home_innings)

#     @property
#     def top(self):
#         """Return True if the current inning is the top of the inning."""
#         return len(self.away_innings) != len(self.home_innings)

#     def score_run(self):
#         """Add a run to the last inning in list."""
#         if self.top:
#             self.away_innings[-1] += 1
#         else:
#             self.home_innings[-1] += 1

#     def new_inning(self):
#         """Add a new inning score to the list."""
#         if self.top:
#             self.home_innings.append(0)
#         else:
#             self.away_innings.append(0)
