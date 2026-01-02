class Stats(object):
    """Root statistics object"""

    def __init__(self):
        """Initialize the statistics."""
        self.batting = BattingStats()
        self.pitching = PitchingStats()

    def __str__(self):
        """Return the string representation of the statistics."""
        return f"{self.batting}\n\n" f"{self.pitching}"

    def add(self, other):
        """Add the statistics from another object."""
        self.batting.add(other.batting)
        self.pitching.add(other.pitching)


class BattingStats(object):
    """The batting statistics object"""

    def __init__(self):
        """Initialize the batting statistics."""
        self.rbi = 0
        self.hbp = 0
        self.at_bats = 0
        self.hits = 0
        self.doubles = 0
        self.triples = 0
        self.home_runs = 0
        self.walks = 0
        self.strike_outs = 0
        self.sac_flys = 0
        self.sac_bunts = 0
        self.gdp = 0
        self.gtp = 0
        self.runs = 0
        self.sb = 0
        self.cs = 0
        self.pickoffs = 0

    def __repr__(self):
        """Return the representation of the batting statistics."""
        return (
            f"<BattingStats AB={self.at_bats} "
            f"H={self.hits} HR={self.home_runs} "
            f"RBI={self.rbi}>"
        )

    def __str__(self):
        """Return the string representation of the batting statistics."""
        return (
            "Batting Stats:\n"
            f"  AB: {self.at_bats}\n"
            f"  H: {self.hits}\n"
            f"  2B: {self.doubles}\n"
            f"  3B: {self.triples}\n"
            f"  HR: {self.home_runs}\n"
            f"  R: {self.runs}\n"
            f"  RBI: {self.rbi}\n"
            f"  BB: {self.walks}\n"
            f"  K: {self.strike_outs}\n"
            f"  HBP: {self.hbp}\n"
            f"  SAC: {self.sac_flys}\n"
            f"  SAB: {self.sac_bunts}\n"
            f"  SB: {self.sb}\n"
            f"  CS: {self.cs}\n"
            f"  PO: {self.pickoffs}\n"
            f"  GDP: {self.gdp}\n"
            f"  GTP: {self.gtp}"
        )

    def add(self, other):
        """Used for aggregating stats, or adding an entire stat instance to
        another.
        """
        for attr in vars(self):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    @property
    def batting_average(self):
        """Return the batting average."""
        return self.hits / self.at_bats

    @property
    def singles(self):
        """Return the number of singles."""
        return self.hits - self.home_runs - self.triples - self.doubles

    @property
    def total_bases(self):
        """Return the total number of bases."""
        return self.triples * 3 + self.doubles * 2 + self.home_runs * 4 + self.singles

    @property
    def slugging(self):
        """The rate of total bases per at bat."""
        return self.total_bases / self.at_bats

    @property
    def obp(self):
        """On Base Percentage. The rate at which a batter reached base
        in his plate appearances.
        """
        return (self.hits + self.walks + self.hbp) / (
            self.at_bats + self.walks + self.hbp + self.sac_flys
        )

    @property
    def ops(self):
        """The sum of On Base Percentage and Slugging."""
        return self.obp + self.slugging

    @property
    def babip(self):
        """Batting average on Balls in Play.
        A measure of a player's batting average exclusively on balls
        hit into the field of play, removing outcomes not affected
        by the opposing defense (namely home runs and streikeouts)
        """
        return (self.hits - self.home_runs) / (
            self.at_bats - self.strike_outs - self.home_runs + self.sac_flys
        )

    def hit_rbi(self):
        """Add a run to the RBI."""
        self.rbi += 1

    def hit_batter(self):
        """Add a hit to the batter."""
        self.hbp += 1

    def steal(self):
        """Add a stolen base."""
        self.sb += 1

    def caught_stealing(self):
        """Add a caught stealing."""
        self.cs += 1

    def pick_off(self):
        """Add a pick off."""
        self.pickoffs += 1

    def at_bat(self):
        """Add an at bat."""
        self.at_bats += 1

    def home_run(self):
        """Add a home run."""
        self.home_runs += 1

    def double(self):
        """Add a double."""
        self.doubles += 1

    def triple(self):
        """Add a triple."""
        self.triples += 1

    def hit(self):
        """Add a hit."""
        self.hits += 1

    def ground_double_play(self):
        """Add a ground double play."""
        self.gdp += 1

    def ground_triple_play(self):
        """Add a ground triple play."""
        self.gtp += 1

    def strike_out(self):
        """Add a strike out."""
        self.strike_outs += 1

    def sac_fly(self):
        """Add a sac fly."""
        self.sac_flys += 1

    def sac_bunt(self):
        """Add a sac bunt."""
        self.sac_bunts += 1

    def run(self, runner):
        """Add a run."""
        self.runs += 1

    def walk(self):
        """Add a walk."""
        self.walks += 1


class PitchingStats(object):
    """The pitching statistics object."""

    def __init__(self):
        """Initialize the pitching statistics."""
        self.hb = 0
        self.hits = 0
        self.doubles = 0
        self.triples = 0
        self.home_runs = 0
        self.walks = 0
        self.strike_outs = 0
        self.runs = 0
        self.pickoffs = 0
        self.outs = 0
        self.balks = 0
        self.wild_pitches = 0

    @property
    def ip_float(self):
        """Return the innings pitched as a float."""
        return self.outs / 3.0

    @property
    def ip_str(self):
        """Return the innings pitched as a string."""
        innings = self.outs // 3
        remainder = self.outs % 3
        return f"{innings}.{remainder}"

    @property
    def era(self):
        """Return the earned run average."""
        return self.runs / self.ip_float * 9 if self.ip_float > 0 else 0

    @property
    def whip(self):
        """Return the walks plus hits per inning pitched."""
        return (self.walks + self.hits) / self.ip_float if self.ip_float > 0 else 0

    def __str__(self):
        """Return the string representation of the pitching statistics."""
        return (
            "Pitching Stats:\n"
            f"  IP: {self.ip_str()}\n"
            f"  H: {self.hits}\n"
            f"  R: {self.runs}\n"
            f"  HR: {self.home_runs}\n"
            f"  HBP: {self.hb}\n"
            f"  BB: {self.walks}\n"
            f"  K: {self.strike_outs}\n"
            f"  2B: {self.doubles}\n"
            f"  3B: {self.triples}\n"
            f"  PO: {self.pickoffs}\n"
            f"  Balk: {self.balks}\n"
            f"  WP: {self.wild_pitches}\n"
        )

    def __repr__(self):
        """Return the representation of the pitching statistics."""
        return (
            f"<PitchingStats "
            f"H={self.hits} HR={self.home_runs} "
            f"R={self.runs} BB={self.walks} "
            f"K={self.strike_outs}>"
        )

    def add(self, other):
        """Add the pitching statistics from another object."""
        for attr in vars(self):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    def hit_batter(self):
        """Add a hit to the batter."""
        self.hb += 1

    def hit(self):
        """Add a hit."""
        self.hits += 1

    def double(self):
        """Add a double."""
        self.doubles += 1

    def triple(self):
        """Add a triple."""
        self.triples += 1

    def home_run(self):
        """Add a home run."""
        self.home_runs += 1

    def walk(self):
        """Add a walk."""
        self.walks += 1

    def strike_out(self):
        """Add a strike out."""
        self.strike_outs += 1

    def run(self):
        """Add a run."""
        self.runs += 1

    def pick_off(self):
        """Add a pick off."""
        self.pickoffs += 1

    def out(self):
        """Add an out."""
        self.outs += 1

    def balk(self):
        """Add a balk."""
        self.balks += 1

    def wild_pitch(self):
        """Add a wild pitch."""
        self.wild_pitches += 1


class SeasonStats(object):
    """The season statistics object."""

    def __init__(self):
        """Initialize the season statistics."""
        self.stats = Stats()
        self.games_played = 0

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
