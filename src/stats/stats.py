class Stats(object):
    """Root statistics object"""
    def __init__(self):
        self.batting = BattingStats()
        self.pitching = PitchingStats()


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
    
    def strike_out(self):
        self.strike_outs += 1

    def hit_batter(self):
        self.hb += 1
    

class TeamStats(object):
    pass
