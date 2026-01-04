class ScoreFormatter(object):
    def __init__(self):
        pass

    def inning_score_str(score, home, away):
        """This will print out a 9 inning display of the score."""
        home_hits = 0
        home_errors = 0
        for player in home.players:
            home_hits += player.stats.batting.hits
            home_errors += player.stats.fielding.errors
        away_hits = 0
        away_errors = 0
        for player in away.players:
            away_hits += player.stats.batting.hits
            away_errors += player.stats.fielding.errors

        output = "\n"
        inn_number = max(len(score.away_innings), 9)
        for _ in range(inn_number):
            output += "{}".format(f"{_ + 1:>3}")
        output += "  R  H  E"
        output += "\n"
        output += "-" * (inn_number + 3) * 3
        output += "\n"
        for _ in range(inn_number):
            try:
                output += "{}".format(f"{score.away_innings[_]:>3}")
            except IndexError:
                output += "   "
        output += "{}".format(f"{score.away:>3}")
        output += "{}".format(f"{away_hits:>3}")
        output += "{}".format(f"{away_errors:>3}")
        output += "\n"
        for _ in range(inn_number):
            try:
                output += "{}".format(f"{score.home_innings[_]:>3}")
            except IndexError:
                output += "   "
        output += "{}".format(f"{score.home:>3}")
        output += "{}".format(f"{home_hits:>3}")
        output += "{}".format(f"{home_errors:>3}")
        return output
