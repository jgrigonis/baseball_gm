class Stats(object):
    """Root statistics object"""

    def __init__(self):
        self.batting = BattingStats()
        self.pitching = PitchingStats()

    def __str__(self):
        return f"{self.batting}\n\n" f"{self.pitching}"

    def add(self, other):
        self.batting.add(other.batting)
        self.pitching.add(other.pitching)


class BattingStats(object):
    """The statistics object"""

    def __init__(self):
        self.rbi = 0
        self.hbp = 0
        self.at_bats = 0
        self.hits = 0
        self.doubles = 0
        self.triples = 0
        self.home_runs = 0
        self.walks = 0
        self.strike_outs = 0
        self.sacrifices = 0
        self.gdp = 0
        self.gtp = 0
        self.runs = 0
        self.sb = 0
        self.cs = 0
        self.pickoffs = 0

    def __repr__(self):
        return (
            f"<BattingStats AB={self.at_bats} "
            f"H={self.hits} HR={self.home_runs} "
            f"RBI={self.rbi}>"
        )

    def __str__(self):
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
            f"  SAC: {self.sacrifices}\n"
            f"  SB: {self.sb}\n"
            f"  CS: {self.cs}\n"
            f"  PO: {self.pickoffs}\n"
            f"  GDP: {self.gdp}\n"
            f"  GTP: {self.gtp}"
        )

    def add(self, other):
        for attr in vars(self):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    @property
    def batting_average(self):
        return self.hits / self.at_bats

    @property
    def singles(self):
        return self.hits - self.home_runs - self.triples - self.doubles

    @property
    def total_bases(self):
        return self.triples * 3 + self.doubles * 2 + self.home_runs * 4 + self.singles

    @property
    def slugging(self):
        return self.total_bases / self.at_bats

    @property
    def obp(self):
        return (self.hits + self.walks + self.hbp) / (
            self.at_bats + self.walks + self.hbp + self.sacrifices
        )

    @property
    def ops(self):
        return self.obp + self.slugging

    def hit_rbi(self):
        self.rbi += 1

    def hit_batter(self):
        self.hbp += 1

    def steal(self):
        self.sb += 1

    def caught_stealing(self):
        self.cs += 1

    def pick_off(self):
        self.pickoffs += 1

    def at_bat(self):
        self.at_bats += 1

    def home_run(self):
        self.home_runs += 1

    def double(self):
        self.doubles += 1

    def triple(self):
        self.triples += 1

    def hit(self):
        self.hits += 1

    def ground_double_play(self):
        self.gdp += 1

    def ground_triple_play(self):
        self.gtp += 1

    def strike_out(self):
        self.strike_outs += 1

    def sacrifice(self):
        self.sacrifices += 1

    def run(self, runner):
        self.runs += 1

    def walk(self):
        self.walks += 1


class PitchingStats(object):
    def __init__(self):
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
        return self.outs / 3.0

    @property
    def ip_str(self):
        innings = self.outs // 3
        remainder = self.outs % 3
        return f"{innings}.{remainder}"

    def __str__(self):
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
        return (
            f"<PitchingStats "
            f"H={self.hits} HR={self.home_runs} "
            f"R={self.runs} BB={self.walks} "
            f"K={self.strike_outs}>"
        )

    def add(self, other):
        for attr in vars(self):
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    def hit_batter(self):
        self.hb += 1

    def hit(self):
        self.hits += 1

    def double(self):
        self.doubles += 1

    def triple(self):
        self.triples += 1

    def home_run(self):
        self.home_runs += 1

    def walk(self):
        self.walks += 1

    def strike_out(self):
        self.strike_outs += 1

    def run(self):
        self.runs += 1

    def pick_off(self):
        self.pickoffs += 1

    def out(self):
        self.outs += 1

    def balk(self):
        self.balks += 1

    def wild_pitch(self):
        self.wild_pitches += 1


class SeasonStats(object):
    def __init__(self):
        self.stats = Stats()
        self.games_played = 0

    def add_game(self, game_stats):
        self.stats.add(game_stats)
        self.games_played += 1


class CareerStats(object):
    def __init__(self):
        self.stats = Stats()
        self.seasons_played = 0

    def add_season(self, season_stats):
        self.stats.add(season_stats.stats)
        self.seasons_played += 1
