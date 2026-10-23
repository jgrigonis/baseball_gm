# src/stats/batting_stats.py
from dataclasses import dataclass, field
import logging

from src.stats import formulas


@dataclass
class BattingStats:
    """The batting statistics object"""

    # Game participation
    game_played: int = 0
    game_started: int = 0

    # Plate appearance outcomes
    at_bats: int = 0
    hits: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    walks: int = 0
    intentional_walks: int = 0
    strike_outs: int = 0
    hbp: int = 0
    sac_flys: int = 0
    sac_bunts: int = 0
    catcher_interferences: int = 0

    # Results
    rbi: int = 0
    runs: int = 0
    plate_appearances: int = 0

    # Baserunning
    sb: int = 0
    cs: int = 0
    pickoffs: int = 0

    # Double/triple plays
    gdp: int = 0
    gtp: int = 0

    # Non-serialized
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("game.stats"),
        repr=False,
        compare=False,
    )

    def __str__(self):
        """Return the string representation of the batting statistics."""
        return (
            "Batting Stats:\n"
            f"  G: {self.game_played} (GS: {self.game_started})\n"
            f"  AB: {self.at_bats}\n"
            f"  H: {self.hits}\n"
            f"  2B: {self.doubles}\n"
            f"  3B: {self.triples}\n"
            f"  HR: {self.home_runs}\n"
            f"  R: {self.runs}\n"
            f"  PA: {self.plate_appearances}\n"
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
        """Used for aggregating stats, or adding an entire stat instance to another."""
        for attr in vars(self):
            # Skip non-numeric attributes like loggers
            if attr.startswith("_") or attr == "logger":
                continue
            setattr(self, attr, getattr(self, attr) + getattr(other, attr))

    @property
    def batting_average(self):
        """Return the batting average."""
        return formulas.batting_average(self.hits, self.at_bats)

    @property
    def singles(self):
        """Return the number of singles."""
        return self.hits - self.home_runs - self.triples - self.doubles

    @property
    def total_bases(self):
        """Return the total number of bases."""
        return formulas.total_bases(
            self.hits, self.doubles, self.triples, self.home_runs
        )

    @property
    def slugging(self):
        """The rate of total bases per at bat."""
        return formulas.slugging_pct(self.total_bases, self.at_bats)

    @property
    def obp(self):
        """On Base Percentage: (H + BB + HBP) / (AB + BB + HBP + SF)."""
        return formulas.on_base_pct(
            self.hits, self.walks, self.hbp, self.at_bats, self.sac_flys
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
        by the opposing defense (namely home runs and strikeouts)
        """
        return (
            (self.hits - self.home_runs)
            / (
                self.at_bats
                - self.strike_outs
                - self.home_runs
                + self.sac_flys
                + self.sac_bunts
            )
            if self.at_bats
            - self.strike_outs
            - self.home_runs
            + self.sac_flys
            + self.sac_bunts
            > 0
            else 0.0
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

    def pickoff(self):
        """Add a pick off."""
        self.pickoffs += 1

    def at_bat(self):
        """Add an at bat."""
        self.logger.trace("ATBAT")
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

    def run(self):
        """Add a run."""
        self.runs += 1

    def walk(self):
        """Add a walk."""
        self.walks += 1

    def plate_appearance(self):
        """Add a plate appearance."""
        self.logger.trace("PLATE_APPEARANCE")
        self.plate_appearances += 1

    def catcher_interference(self):
        """Add a catcher interference."""
        self.catcher_interferences += 1

    def intentional_walk(self):
        """Add an intentional walk."""
        self.intentional_walks += 1
