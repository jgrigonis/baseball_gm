# src/league/hall_of_fame.py
"""
The Hall of Fame: who's eligible, what the writers see in a career, and how
they vote (plans/hall-of-fame.md). Pure rules; the database side is
src/api/services/hall_of_fame.py.

The BBWAA's rules, scaled to our leagues:
  - 10 major league seasons (backstory seasons count) and 5 full seasons
    retired. Players who retired before the league's first played season
    never go on a ballot.
  - A screening committee lets first-timers with real credentials onto the
    ballot; holdovers come back with 5% of the vote or more.
  - Each writer votes for up to 10. 75% elects, under 5% drops a player,
    and 10 years on the ballot is the limit.

Everything the writers look at counts a backstory season at half, so the
Hall isn't crowded with players whose best years were made up before the
league started.

The writers are two beat writers per team, made up from the league's id
the same way every time. Each leans one way (career value, milestones,
awards, or a small Hall), has his own bar, a little noise per player, a
soft spot for players from the team he covers, and warms to holdovers the
longer they stay on the ballot.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

MIN_SEASONS = 10
WAIT_SEASONS = 5
MAX_BALLOT_YEARS = 10
ELECT_SHARE = 0.75
KEEP_SHARE = 0.05
MAX_VOTES = 10
WRITERS_PER_TEAM = 2

BACKSTORY_WEIGHT = 0.5
PEAK_SEASONS = 7

# What a Hall of Famer's numbers look like. A score of 1.0 against these is
# a borderline Hall of Famer in a writer's eyes; see the calibration notes in
# plans/hall-of-fame.md.
JAWS_HITTER = 54.0
JAWS_STARTER = 48.0
JAWS_RELIEVER = 23.0
MILESTONES = {  # weighted career totals
    "hits": 3000,
    "hr": 500,
    "wins": 230,
    "k": 3200,
    "saves": 450,
}
ALL_STAR_STANDARD = 11.0
AWARD_STANDARD = 28.0
AWARD_POINTS = {
    "mvp": 6.0,
    "cy_young": 6.0,
    "reliever": 2.5,
    "finals_mvp": 2.0,
    "semis_mvp": 1.0,
    "hank_aaron": 1.5,
    "edgar_martinez": 1.0,
    "batting_champ": 1.0,
    "era_champ": 1.0,
    "wins_champ": 0.5,
    "gold_glove": 1.0,
    "platinum_glove": 1.5,
    "silver_slugger": 1.0,
    "roy": 1.0,
}
ALL_STAR_POINTS = 1.0
RING_POINTS = 0.5

# Screening committee: a first-timer needs one of these to make the ballot.
SCREEN_WAR = 20.0
SCREEN_ALL_STARS = 5.0
SCREEN_MILESTONE = 0.85  # this share of a milestone
SCREEN_AWARDS = ("mvp", "cy_young")


# ── A career, as the writers see it ──────────────────────────────────────────


@dataclass
class Season:
    year: int
    backstory: bool
    war: float = 0.0
    hitter: bool = True
    games: int = 0
    starts: int = 0  # pitching starts
    hits: int = 0
    hr: int = 0
    wins: int = 0
    k: int = 0
    saves: int = 0
    ab: int = 0
    outs: int = 0
    er: int = 0
    team_id: str | None = None
    ring: bool = False

    @property
    def weight(self) -> float:
        return BACKSTORY_WEIGHT if self.backstory else 1.0


@dataclass
class Honor:
    """An award or an All-Star selection."""

    key: str  # an award key, or "all_star"
    year: int
    backstory: bool

    @property
    def weight(self) -> float:
        return BACKSTORY_WEIGHT if self.backstory else 1.0


@dataclass
class Career:
    player_id: str
    seasons: list[Season]
    honors: list[Honor] = field(default_factory=list)
    teams: dict[str, str] = field(default_factory=dict)  # team_id -> name, for writers

    @property
    def num_seasons(self) -> int:
        return len({s.year for s in self.seasons if s.games > 0})

    @property
    def hitter(self) -> bool:
        hit = sum(s.games for s in self.seasons if s.hitter)
        pitch = sum(s.games for s in self.seasons if not s.hitter)
        return hit >= pitch

    @property
    def reliever(self) -> bool:
        if self.hitter:
            return False
        games = sum(s.games for s in self.seasons if not s.hitter)
        starts = sum(s.starts for s in self.seasons if not s.hitter)
        return games > 0 and starts < 0.3 * games

    def total(self, stat: str) -> float:
        """A counting stat, backstory seasons at half."""
        return sum(getattr(s, stat) * s.weight for s in self.seasons)

    def raw_total(self, stat: str) -> int:
        return sum(getattr(s, stat) for s in self.seasons)

    @property
    def war(self) -> float:
        return sum(s.war * s.weight for s in self.seasons)

    @property
    def raw_war(self) -> float:
        return sum(s.war for s in self.seasons)

    @property
    def peak(self) -> float:
        """His best seven seasons' WAR, weighted."""
        best = sorted((s.war * s.weight for s in self._by_year()), reverse=True)
        return sum(best[:PEAK_SEASONS])

    @property
    def jaws(self) -> float:
        return (self.war + self.peak) / 2

    def _by_year(self) -> list[Season]:
        """One season per year (a traded player's stints added together)."""
        out: dict[int, Season] = {}
        for s in self.seasons:
            if s.year in out:
                o = out[s.year]
                o.war += s.war
            else:
                out[s.year] = Season(s.year, s.backstory, war=s.war)
        return list(out.values())

    def honors_count(self, key: str, weighted: bool = True) -> float:
        return sum((h.weight if weighted else 1) for h in self.honors if h.key == key)

    @property
    def rings(self) -> float:
        return sum(s.weight for s in self._ring_years())

    def _ring_years(self) -> list[Season]:
        seen, out = set(), []
        for s in self.seasons:
            if s.ring and s.year not in seen:
                seen.add(s.year)
                out.append(s)
        return out

    @property
    def raw_rings(self) -> int:
        return len(self._ring_years())

    @property
    def first_year(self) -> int:
        return min(s.year for s in self.seasons)

    @property
    def last_year(self) -> int:
        return max(s.year for s in self.seasons)

    def main_team(self) -> str | None:
        """The team he gave the most to: WAR there, then games."""
        by: dict[str, list[float]] = {}
        for s in self.seasons:
            if s.team_id:
                v = by.setdefault(s.team_id, [0.0, 0.0])
                v[0] += max(s.war, 0.0) * s.weight
                v[1] += s.games
        if not by:
            return None
        return max(by, key=lambda t: (by[t][0], by[t][1]))

    def team_ids(self) -> set[str]:
        return {s.team_id for s in self.seasons if s.team_id}

    # ── The three ways of looking at him ─────────────────────────────────────

    def value_score(self) -> float:
        """Career value against a Hall of Famer's: JAWS-style."""
        if self.reliever:
            standard = JAWS_RELIEVER
        elif self.hitter:
            standard = JAWS_HITTER
        else:
            standard = JAWS_STARTER
        return max(self.jaws, 0.0) / standard

    def milestone_share(self) -> float:
        """How close he came to his best milestone (1.0 = reached it)."""
        if self.hitter:
            keys = ("hits", "hr")
        else:
            keys = ("wins", "k", "saves")
        return max(self.total(k) / MILESTONES[k] for k in keys)

    def counting_score(self) -> float:
        """A traditionalist's view: milestones, All-Star picks, rings."""
        stars = self.honors_count("all_star") / ALL_STAR_STANDARD
        return 0.6 * self.milestone_share() + 0.35 * stars + 0.05 * min(self.rings, 3)

    def award_points(self) -> float:
        pts = sum(AWARD_POINTS.get(h.key, 0.0) * h.weight for h in self.honors)
        pts += ALL_STAR_POINTS * self.honors_count("all_star")
        pts += RING_POINTS * self.rings
        return pts

    def award_score(self) -> float:
        return self.award_points() / AWARD_STANDARD


# ── Eligibility and the ballot ──────────────────────────────────────────────


def eligible(career: Career, retired_year: int, election_year: int) -> bool:
    """10 seasons played and 5 full seasons retired (retired after
    retired_year, so his first ballot comes after retired_year + 5)."""
    return (
        career.num_seasons >= MIN_SEASONS
        and election_year - retired_year >= WAIT_SEASONS
    )


def passes_screening(career: Career) -> bool:
    """The screening committee's call on a first-timer."""
    if career.war >= SCREEN_WAR:
        return True
    if career.honors_count("all_star") >= SCREEN_ALL_STARS:
        return True
    if career.milestone_share() >= SCREEN_MILESTONE:
        return True
    return any(career.honors_count(k, weighted=False) for k in SCREEN_AWARDS)


@dataclass
class Candidate:
    career: Career
    year_on_ballot: int  # 1 for a first-timer
    last_share: float = 0.0  # last year's vote share (0 for a first-timer)

    @property
    def final_year(self) -> bool:
        return self.year_on_ballot >= MAX_BALLOT_YEARS


# ── The writers ─────────────────────────────────────────────────────────────

LEANS = ("value", "counting", "awards", "small")
LEAN_WEIGHTS = (0.35, 0.25, 0.2, 0.2)
# How each lean blends the three views (value, counting, awards).
LEAN_MIX = {
    "value": (0.7, 0.15, 0.15),
    "counting": (0.25, 0.55, 0.2),
    "awards": (0.3, 0.2, 0.5),
    "small": (0.5, 0.25, 0.25),
}
BAR = {"value": 1.0, "counting": 1.0, "awards": 1.0, "small": 1.15}
BAR_SPREAD = 0.06
NOISE = 0.07  # each writer's own read of each player
HOMER = 0.05  # a player who played for the writer's team
HOLDOVER_WARMING = 0.012  # per earlier year on the ballot
MOMENTUM = 0.08  # times (last year's share - 0.5): a rising candidate rises
FINAL_YEAR_PUSH = 0.04
STANDOUT = 0.75  # a career this share of its best view, whatever the lean


@dataclass
class Writer:
    name: str
    outlet: str
    team_id: str
    lean: str
    bar: float

    def score(self, c: Candidate, rng: random.Random) -> float:
        mix = LEAN_MIX[self.lean]
        cr = c.career
        views = (cr.value_score(), cr.counting_score(), cr.award_score())
        base = sum(m * v for m, v in zip(mix, views))
        # Overwhelming on any one count wins every writer over.
        base = max(base, STANDOUT * max(views))
        s = base + rng.gauss(0.0, NOISE)
        if self.team_id in cr.team_ids():
            s += HOMER
        if c.year_on_ballot > 1:
            s += HOLDOVER_WARMING * (c.year_on_ballot - 1)
            s += MOMENTUM * (c.last_share - 0.5)
        if c.final_year:
            s += FINAL_YEAR_PUSH
        return s

    def ballot(self, cands: list[Candidate], rng: random.Random) -> list[str]:
        """The player ids he votes for: everyone over his bar, best first,
        ten at most."""
        scored = [(self.score(c, rng), c.career.player_id) for c in cands]
        yes = sorted((s, pid) for s, pid in scored if s >= self.bar)
        yes.reverse()
        return [pid for _, pid in yes[:MAX_VOTES]]


OUTLETS = (
    "Herald",
    "Courier",
    "Tribune",
    "Gazette",
    "Post",
    "Ledger",
    "Star",
    "Times",
    "Chronicle",
    "Dispatch",
    "Sentinel",
    "Journal",
)


def writers(league_id: str, teams: list[tuple[str, str]], make_name) -> list[Writer]:
    """Two beat writers per team, the same ones every time for a league.
    teams: (team_id, city), sorted by id. make_name(rng) gives "First Last"."""
    rng = random.Random(f"hof-writers-{league_id}")
    out = []
    for team_id, city in sorted(teams):
        for _ in range(WRITERS_PER_TEAM):
            lean = rng.choices(LEANS, LEAN_WEIGHTS)[0]
            out.append(
                Writer(
                    name=make_name(rng),
                    outlet=f"{city} {rng.choice(OUTLETS)}",
                    team_id=team_id,
                    lean=lean,
                    bar=BAR[lean] + rng.gauss(0.0, BAR_SPREAD),
                )
            )
    return out


# ── An election ─────────────────────────────────────────────────────────────


@dataclass
class Result:
    player_id: str
    votes: int
    share: float
    year_on_ballot: int
    outcome: str  # elected / returning / dropped / final


def elect(
    cands: list[Candidate], voters: list[Writer], rng: random.Random
) -> tuple[int, list[Result]]:
    """Every writer fills in a ballot. Returns (ballots cast, results), the
    results most votes first."""
    votes = {c.career.player_id: 0 for c in cands}
    cast = 0
    for w in voters:
        cast += 1
        for pid in w.ballot(cands, rng):
            votes[pid] += 1
    out = []
    for c in cands:
        pid = c.career.player_id
        share = votes[pid] / cast if cast else 0.0
        if cast and votes[pid] >= math.ceil(ELECT_SHARE * cast - 1e-9):
            outcome = "elected"
        elif c.final_year:
            outcome = "final"
        elif share < KEEP_SHARE:
            outcome = "dropped"
        else:
            outcome = "returning"
        out.append(Result(pid, votes[pid], share, c.year_on_ballot, outcome))
    out.sort(key=lambda r: (-r.votes, r.player_id))
    return cast, out
