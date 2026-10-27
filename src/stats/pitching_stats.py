# src/stats/pitching_stats.py
from dataclasses import dataclass

from src.stats import formulas


@dataclass
class PitchingStats:
    """The pitching statistics object."""

    # Game participation
    game_played: int = 0
    game_started: int = 0
    complete_game: int = 0
    shut_out: int = 0
    no_hitter: int = 0

    # Win/Loss/Save
    win: int = 0
    loss: int = 0
    save: int = 0
    hold: int = 0

    # Outs and innings
    outs: int = 0

    # Hits allowed
    hits: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0

    # Runs and walks
    runs: int = 0
    earned_runs: int = 0
    walks: int = 0
    intentional_walks: int = 0
    hb: int = 0  # Hit batters

    # Strikeouts and outs
    strike_outs: int = 0
    ground_double_plays: int = 0

    # Baserunning plays
    pickoffs: int = 0

    # Pitcher mistakes
    balks: int = 0
    wild_pitches: int = 0
    illegal_pitches: int = 0

    # Pitch count
    pitch_count: int = 0

    @property
    def ip_float(self):
        """Return the innings pitched as a float."""
        return formulas.innings(self.outs)

    @property
    def ip_str(self):
        """Return the innings pitched as a string."""
        return formulas.ip_str(self.outs)

    @property
    def era(self):
        """Return the earned run average."""
        return formulas.era(self.earned_runs, self.outs)

    @property
    def whip(self):
        """Return the walks plus hits per inning pitched."""
        return formulas.whip(self.hits, self.walks, self.outs)

    def __str__(self):
        """Return the string representation of the pitching statistics."""
        return (
            "Pitching Stats:\n"
            f"  G: {self.game_played} (GS: {self.game_started}, CG: {self.complete_game}, SHO: {self.shut_out}, NH: {self.no_hitter})\n"
            f"  W-L: {self.win}-{self.loss} (SV: {self.save}, HLD: {self.hold})\n"
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
            f"  ERA: {self.era:.2f}\n"
            f"  WHIP: {self.whip:.2f}"
        )

    def add(self, other):
        """Used for aggregating stats, or adding an entire stat instance to another."""
        for attr in vars(self):
            # Skip non-numeric attributes
            if attr.startswith("_"):
                continue
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

    def earned_run(self):
        """Add an earned run."""
        self.earned_runs += 1

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
        """Add an illegal pitch."""
        self.illegal_pitches += 1

    def pitch(self):
        """Add one to pitch count."""
        self.pitch_count += 1

    def ground_double_play(self):
        """Add a ground double play."""
        self.ground_double_plays += 1

    def intentional_walk(self):
        """Add an intentional walk."""
        self.intentional_walks += 1
