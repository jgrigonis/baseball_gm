# src/league/offseason/draft_strategy.py
"""
Draft strategy: need chips, an age preference and a short pinned list that
steer a GM's picks instead of a hand-ordered list of the whole pool.

Scoring at each pick:

    score = prospect_rating + min(BONUS_CAP, Σ LEVEL_POINTS[level] × fit)
            + age_adjust

Fit (0 to 1) is how much a player stands out in the chip's rating compared
with the rest of this year's pool. A chip only applies to the players it is
about: a position chip to players whose best spot is that position (a listed
2B who rates best at SS counts as IF), a hitting archetype to hitters, Ace SP
to starters and Relief Ace to relievers. Position chips ask "do we have a
body here" so their window starts at the median; archetype chips ask for
someone special so theirs starts higher.

Each chip is Low, Medium or High. Low adds nothing, so it's a chip that isn't
a need. Needs wear off: once a pick fills a chip (fit ≥ FILL_FIT), that chip
drops a level for the rest of the draft.

Ratings are 0-100 and one letter grade is 5 points, so at High a chip is worth
up to about one grade and all chips together about 1.5 grades. These are
starting values to tune by playtesting (scripts/draft_strategy_preview.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord

LOW, MED, HIGH = 0, 1, 2
LEVEL_POINTS = {LOW: 0, MED: 3, HIGH: 6}
BONUS_CAP = 8
AGE_POINTS = 2  # the slider at either end moves a player by up to this much
FILL_FIT = 0.5
MAX_PINS = 10

# Fit windows as (low, high) percentiles of the players a chip applies to.
POSITION_WINDOW = (0.50, 0.80)
ARCHETYPE_WINDOW = (0.75, 0.97)

HITTER_GROUPS = ("c", "if", "of")
ROTATION = 5  # starters a team has room for
HITTERS = "hitters"


@dataclass(frozen=True)
class Chip:
    key: str
    label: str
    rating: str  # key into ratings() below
    group: str  # who it applies to: a group from group() below, or HITTERS
    window: tuple[float, float]


CHIPS: dict[str, Chip] = {
    c.key: c
    for c in [
        # Positions are broad: a listed 2B may turn out to be your best SS.
        Chip("c", "C", "c", "c", POSITION_WINDOW),
        Chip("if", "IF", "if", "if", POSITION_WINDOW),
        Chip("of", "OF", "of", "of", POSITION_WINDOW),
        Chip("sp", "SP", "sp", "sp", POSITION_WINDOW),
        Chip("rp", "RP", "rp", "rp", POSITION_WINDOW),
        # Archetypes
        Chip("lead_off", "Lead Off", "lead_off", HITTERS, ARCHETYPE_WINDOW),
        Chip("contact", "Contact Hitter", "contact_hitter", HITTERS, ARCHETYPE_WINDOW),
        Chip("power", "Power Hitter", "power_hitter", HITTERS, ARCHETYPE_WINDOW),
        Chip(
            "offense", "Overall Offense", "overall_offense", HITTERS, ARCHETYPE_WINDOW
        ),
        Chip("speed", "Speed", "speed_runner", HITTERS, ARCHETYPE_WINDOW),
        Chip("ace_sp", "Ace SP", "sp", "sp", ARCHETYPE_WINDOW),
        Chip("relief_ace", "Relief Ace", "rp", "rp", ARCHETYPE_WINDOW),
    ]
}


def ratings(player: PlayerRecord) -> dict[str, int]:
    """PlayerEvaluator's ratings plus the IF and OF composites."""
    r = PlayerEvaluator.rate_player(player.skills, player.throws)
    r["if"] = max(r["2b"], r["3b"], r["ss"])
    r["of"] = max(r["lf"], r["cf"], r["rf"])
    return r


def group(player: PlayerRecord, r: dict[str, int], staff: str | None = None) -> str:
    """Where a player will most likely play. For pitchers that's `staff`, the
    team's own use of him (sp in the rotation, rp in the bullpen), when he has
    one; otherwise SP if he rates better there than at RP. A pitcher's listed
    SP or RP is only a leaning from when he was generated, and any pitcher can
    do either job.
    Hitters go to whichever of C, IF or OF they rate best at. First base
    counts as infield: there's no 1B chip, and the IF chip's own fit (the
    best of 2B, 3B and SS) still tells a real infielder from a pure 1B."""
    if player.is_pitcher():
        if staff in ("sp", "rp"):
            return staff
        return "sp" if r["sp"] > r["rp"] else "rp"
    return max(HITTER_GROUPS, key=lambda g: max(r[g], r["1b"]) if g == "if" else r[g])


def staff_groups(
    pitchers: list[tuple[PlayerRecord, dict[str, int]]], staff: dict[str, str]
) -> dict[str, str]:
    """{player_id: sp | rp} for one team's major league pitchers. Each goes
    by group(), except that a team only has room for a ROTATION-man rotation:
    once the starters it has named fill it, the best of the rest who lean SP
    take the open spots and any beyond that are really relievers."""
    groups = {p.id: group(p, r, staff.get(p.id)) for p, r in pitchers}
    named = sum(1 for p, _ in pitchers if staff.get(p.id) == "sp")
    leaning_sp = sorted(
        ((p, r) for p, r in pitchers if p.id not in staff and groups[p.id] == "sp"),
        key=lambda x: x[1]["sp"],
        reverse=True,
    )
    for p, _ in leaning_sp[max(0, ROTATION - named) :]:
        groups[p.id] = "rp"
    return groups


@dataclass
class DraftStrategy:
    """A GM's saved strategy. `chips` maps chip key → level (0-2: Low, Medium, High), `age_pref`
    runs from -1 (upside: younger) to 1 (ready sooner: older)."""

    chips: dict[str, int] = field(default_factory=dict)
    age_pref: float = 0.0
    pins: list[str] = field(default_factory=list)

    def __post_init__(self):
        unknown = set(self.chips) - set(CHIPS)
        if unknown:
            raise ValueError(f"Unknown draft chips: {sorted(unknown)}")
        for key, level in self.chips.items():
            if level not in LEVEL_POINTS:
                raise ValueError(f"Chip {key} level must be 0-2, got {level}")
        if not -1.0 <= self.age_pref <= 1.0:
            raise ValueError("age_pref must be between -1 and 1")
        if len(self.pins) > MAX_PINS:
            raise ValueError(f"At most {MAX_PINS} pinned players")

    def copy(self) -> DraftStrategy:
        return DraftStrategy(dict(self.chips), self.age_pref, list(self.pins))

    def has_chips(self) -> bool:
        return any(level > LOW for level in self.chips.values())

    def or_needs(self, needs: dict[str, int]) -> DraftStrategy:
        """This strategy, or with every chip Low, a copy that uses `needs`
        (the suggested chips) instead. Pins and the age slider are kept."""
        if self.has_chips():
            return self
        return DraftStrategy(dict(needs), self.age_pref, list(self.pins))


def _percentile(sorted_vals: list[int], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = q * (len(sorted_vals) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


class StrategyScorer:
    """Precomputes every pool player's prospect rating, age and chip fits
    once, so scoring a pick is cheap."""

    def __init__(self, rated: list[tuple[PlayerRecord, int]]):
        self.order = [p.id for p, _ in rated]  # best prospect rating first
        self.prospect = {p.id: r for p, r in rated}
        self.age = {p.id: p.age for p, _ in rated}
        all_ratings = {p.id: ratings(p) for p, _ in rated}
        self.group = {p.id: group(p, all_ratings[p.id]) for p, _ in rated}

        self.fits: dict[str, dict[str, float]] = {pid: {} for pid in self.order}
        for chip in CHIPS.values():
            kind = [pid for pid in self.order if self._applies(chip, pid)]
            vals = sorted(all_ratings[pid][chip.rating] for pid in kind)
            lo = _percentile(vals, chip.window[0])
            hi = _percentile(vals, chip.window[1])
            span = max(hi - lo, 1.0)
            for pid in kind:
                fit = (all_ratings[pid][chip.rating] - lo) / span
                self.fits[pid][chip.key] = min(1.0, max(0.0, fit))

        ages = self.age.values()
        self._age_lo = min(ages, default=0)
        self._age_span = max(max(ages, default=0) - self._age_lo, 1)

    def _applies(self, chip: Chip, pid: str) -> bool:
        g = self.group[pid]
        return g in HITTER_GROUPS if chip.group == HITTERS else g == chip.group

    def fit(self, pid: str, chip: str) -> float:
        return self.fits[pid].get(chip, 0.0)

    def score(self, pid: str, strategy: DraftStrategy) -> float:
        bonus = sum(
            LEVEL_POINTS[level] * self.fit(pid, key)
            for key, level in strategy.chips.items()
        )
        # Age mapped to -1 (youngest in pool) … 1 (oldest in pool)
        age_pos = 2 * (self.age[pid] - self._age_lo) / self._age_span - 1
        return (
            self.prospect[pid]
            + min(BONUS_CAP, bonus)
            + AGE_POINTS * strategy.age_pref * age_pos
        )

    def choose(self, available: set[str], strategy: DraftStrategy) -> str | None:
        """Highest available pin, else the highest strategy score. Ties go to
        the better prospect rating."""
        for pid in strategy.pins:
            if pid in available:
                return pid
        best, best_score = None, float("-inf")
        for pid in self.order:
            if pid not in available:
                continue
            s = self.score(pid, strategy)
            if s > best_score:
                best, best_score = pid, s
        return best

    def wear_off(self, pid: str, strategy: DraftStrategy) -> None:
        """Drop a level on every chip this pick filled."""
        for key, level in strategy.chips.items():
            if level > LOW and self.fit(pid, key) >= FILL_FIT:
                strategy.chips[key] = level - 1


def project_picks(
    scorer: StrategyScorer,
    draft_order: list[str],
    rounds: int,
    strategies: dict[str, DraftStrategy],
    team_id: str,
    n: int = 5,
    taken_by_others: dict[str, int] | None = None,
) -> list[tuple[int, str]]:
    """Simulate the snake draft in memory and return `team_id`'s first `n`
    picks as (overall pick, player_id). Teams without a strategy take the best
    prospect rating, as AI GMs do. If `taken_by_others` is given, it's filled
    with player_id → overall pick for every other team's pick along the way."""
    available = set(scorer.order)
    working = {tid: s.copy() for tid, s in strategies.items()}
    mine: list[tuple[int, str]] = []
    overall = 1
    for round_num in range(1, rounds + 1):
        order = draft_order if round_num % 2 == 1 else draft_order[::-1]
        for tid in order:
            if not available or len(mine) >= n:
                return mine
            strategy = working.get(tid)
            if strategy is not None:
                pid = scorer.choose(available, strategy)
                scorer.wear_off(pid, strategy)
            else:
                pid = next(p for p in scorer.order if p in available)
            available.discard(pid)
            if tid == team_id:
                mine.append((overall, pid))
            elif taken_by_others is not None:
                taken_by_others[pid] = overall
            overall += 1
    return mine
