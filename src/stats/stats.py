class Stats(object):
    """Root statistics object"""

    def __init__(self):
        self.batting = BattingStats()
        self.pitching = PitchingStats()

    def __str__(self):
        return f"{self.batting}\n\n" f"{self.pitching}"


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

    def ip_str(self):
        innings = self.outs // 3
        remainder = self.outs % 3
        return f"{innings}.{remainder}"

    def __str__(self):
        return (
            "Pitching Stats:\n"
            f"  H: {self.hits}\n"
            f"  2B: {self.doubles}\n"
            f"  3B: {self.triples}\n"
            f"  HR: {self.home_runs}\n"
            f"  R: {self.runs}\n"
            f"  BB: {self.walks}\n"
            f"  K: {self.strike_outs}\n"
            f"  HBP: {self.hb}\n"
            f"  PO: {self.pickoffs}\n"
            f"  IP: {self.ip_str()}\n"
            f"  Balk: {self.balks}\n"
            f"  Balk: {self.wild_pitches}\n"
        )

    def __repr__(self):
        return (
            f"<PitchingStats "
            f"H={self.hits} HR={self.home_runs} "
            f"R={self.runs} BB={self.walks} "
            f"K={self.strike_outs}>"
        )

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
