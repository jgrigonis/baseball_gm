from .batting_stats import BattingStats
from .pitching_stats import PitchingStats
from .fielding_stats import FieldingStats


class Stats(object):
    """Root statistics object"""

    def __init__(self):
        """Initialize the statistics."""
        self.batting = BattingStats()
        self.pitching = PitchingStats()
        self.fielding = FieldingStats()

    def __str__(self):
        """Return the string representation of the statistics."""
        return f"{self.batting}\n\n" f"{self.pitching}\n\n" f"{self.fielding}"

    def add(self, other):
        """Add the statistics from another object."""
        self.batting.add(other.batting)
        self.pitching.add(other.pitching)
        self.fielding.add(other.fielding)


class GameStats(Stats):
    """Stats for a single game."""

    pass


class SeasonStats(object):
    """The season statistics object."""

    def __init__(self, stats, games_played):
        """Initialize the season statistics."""
        self.stats = stats
        self.games_played = games_played

    def add_game(self, game_stats):
        """Add a game to the season statistics."""
        self.stats.add(game_stats)
        self.games_played += 1


class CareerStats(object):
    """The career statistics object."""

    def __init__(self):
        """Initialize the career statistics."""
        self.stats = Stats()
        self.seasons_played = 0
        self.career_games = 0

    def add_season(self, season_stats):
        """Add a season to the career statistics."""
        self.career_games += season_stats.games_played
        self.stats.add(season_stats.stats)
        self.seasons_played += 1
