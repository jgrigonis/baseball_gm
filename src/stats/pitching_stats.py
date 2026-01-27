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
        self.illegal_pitches = 0
        self.pitch_count = 0
        self.ground_double_plays = 0
        self.intentional_walks = 0

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
            f"  IP: {self.ip_str}\n"
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

    def pickoff(self):
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

    def illegal_pitch(self):
        """Add one to pitch count."""
        self.illegal_pitches += 1

    def pitch(self):
        """Add one to pitch count."""
        self.pitch_count += 1

    def ground_double_play(self):
        """Add a ground double play."""
        self.ground_double_play += 1

    def intentional_walk(self):
        """Add an intentional walk."""
        self.intentional_walks += 1
