# src/league/owner_scoring.py
"""
How an owner judges a season, and how safe the GM's job is
(plans/owners.md, "Scoring"). The pure part: src/api/services/owner_review.py
gathers each team's season and stores the verdict.

Each dimension the owner weighs is scored from -1 (badly missed) through 0
(met) to +1 (far beat it), always against what was fair to expect of this
roster, not a raw number. The season's score is those scores times the
owner's weights (normalized), so it's -1 to +1 too.

Job security, 0 to 100, carries from season to season for a GM under one
owner. A new GM starts at a grace level set by the owner's patience. Each
season's score adds to it or takes from it; patience softens the losses, and
a title buys a lot of time. Below HOT_SEAT the GM is on the hot seat; below
FIRE, at a season's end, they're fired, if the league has owner firing on and
the owner's own rules allow it (FiringRules: a honeymoon, a warning first,
credit for a better year than the last).

Speed Blitz has no money, so profit, attendance and fans aren't judged
there; the other weights carry the score. Money is judged by profit alone:
payroll past the budget only matters through what it costs (Josh,
2026-11-06).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.league import owners

# ── The season, as an owner sees it ──────────────────────────────────────────


@dataclass(frozen=True)
class TeamSeason:
    wins: int
    losses: int
    # 0 best to 1 worst, by roster strength before the season (team state).
    rank_before: float = 0.5
    # The same in a couple of years, at the season's end.
    rank_future: float = 0.5
    # Young players not on the big-league roster, by future value.
    farm_rank: float = 0.5
    made_playoffs: bool = False
    rounds_won: int = 0
    champion: bool = False
    # Money: None in a league without budgets (Speed Blitz).
    payroll: int | None = None
    budget: int | None = None
    revenue: int | None = None
    profit: int | None = None
    # What a team in this market would make spending like a middle owner
    # under the league's cap: profit is judged against it, so a small market
    # isn't marked down for being small (None: against PROFIT_TARGET).
    profit_par: int | None = None
    fans_before: int | None = None
    fans_after: int | None = None
    # The season's home crowds as an Attendance reading, -1 to 1
    # (src/league/finances.py attendance_score); None for a season played
    # before crowds were counted, which reads fan interest instead.
    crowd_score: float | None = None
    homegrown_share: float = 0.0
    # The count behind the share: players on the 40-man roster the team
    # drafted itself, and players on it, so the owner can name them.
    homegrown_players: int = 0
    roster_players: int = 0
    all_stars: int = 0
    award_winners: int = 0
    # The league's averages, so homegrown talent and stars are judged
    # against the other teams (None: against fixed marks).
    league_homegrown: float | None = None
    league_star_points: float | None = None
    icons_lost: int = 0
    trades: int = 0
    # Players B- or better the team released: turnover too, at half a trade.
    releases: int = 0
    rival_wins: int = 0
    rival_losses: int = 0

    @property
    def star_points(self) -> float:
        return self.all_stars + 1.5 * self.award_winners

    @property
    def win_pct(self) -> float:
        games = self.wins + self.losses
        return self.wins / games if games else 0.5

    def as_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# What a .500 roster's win % target moves by from the best roster (rank 0) to
# the worst (rank 1), and how much the owner's ambition adds on top.
TARGET_SPREAD = 0.16
AMBITION_PULL = 0.04
# A win % this far off target scores a full +1 or -1.
WIN_SCALE = 0.08
# Rosters this good or better (rank share) are expected to make the playoffs,
# moved by ambition: an ambitious owner expects it of a middling team.
PLAYOFF_RANK = 0.34
# Profit margin (profit / revenue) that's "met", and how far off scores 1.
PROFIT_TARGET = 0.15
PROFIT_SCALE = 0.15


def win_target(rank_before: float, ambition: int) -> float:
    """The win % an owner expects from a roster this strong."""
    base = 0.5 + (0.5 - rank_before) * TARGET_SPREAD * 2
    return base + (ambition - 50) / 50 * AMBITION_PULL


def expects_playoffs(rank_before: float, ambition: int) -> bool:
    return rank_before < PLAYOFF_RANK + (ambition - 50) / 50 * 0.15


def score_dimensions(
    s: TeamSeason, traits: dict, money: bool = True
) -> dict[str, float | None]:
    """Each dimension's score from -1 to +1, or None when it can't be
    judged in this league (no money in Speed Blitz)."""
    t = owners.clean_traits(traits)
    ambition = t["ambition"]
    out: dict[str, float | None] = {}

    out["wins"] = _clamp((s.win_pct - win_target(s.rank_before, ambition)) / WIN_SCALE)

    expected = expects_playoffs(s.rank_before, ambition)
    if s.champion:
        post = 1.0
    elif s.made_playoffs:
        post = 0.3 + 0.25 * s.rounds_won - (0.1 if expected else 0)
    else:
        post = -0.6 if expected else -0.1
    out["postseason"] = _clamp(post)

    has_money = money and s.budget is not None and s.payroll is not None
    if has_money and s.revenue and s.profit is not None:
        if s.profit_par is not None:
            margin = (s.profit - s.profit_par) / s.revenue
            out["profit"] = _clamp(margin / PROFIT_SCALE)
        else:
            margin = s.profit / s.revenue
            out["profit"] = _clamp((margin - PROFIT_TARGET) / PROFIT_SCALE)
    else:
        out["profit"] = None
    if has_money and s.crowd_score is not None:
        out["attendance"] = _clamp(s.crowd_score)
    elif has_money and s.fans_after is not None:
        # Before crowds were counted: a full park is fans who care.
        out["attendance"] = _clamp((s.fans_after - 50) / 30)
    else:
        out["attendance"] = None
    if has_money and s.fans_after is not None:
        before = s.fans_before if s.fans_before is not None else 50
        out["fans"] = _clamp((s.fans_after - before) / 8)
    else:
        out["fans"] = None

    # Two years out, and the farm, against the middle of the league.
    out["future"] = _clamp((0.5 - s.rank_future) * 1.5 + (0.5 - s.farm_rank) * 0.8)
    home_mark = 0.3 if s.league_homegrown is None else s.league_homegrown
    out["homegrown"] = _clamp((s.homegrown_share - home_mark) / 0.25)
    star_mark = 1.5 if s.league_star_points is None else s.league_star_points
    out["stars"] = _clamp((s.star_points - star_mark) / 2.5)
    out["icons"] = _clamp(0.1 - 0.6 * s.icons_lost)
    out["stability"] = _clamp(0.25 - 0.2 * s.trades - 0.1 * s.releases)
    games = s.rival_wins + s.rival_losses
    out["rivalry"] = _clamp((s.rival_wins / games - 0.5) / 0.2) if games else 0.0
    return out


def season_score(scores: dict[str, float | None], weights: dict) -> float:
    """The owner's verdict on the season, -1 to +1: each dimension's score
    times its share of the weights that could be judged."""
    w = owners.clean_weights(weights)
    judged = {k: v for k, v in scores.items() if v is not None and w.get(k)}
    total = sum(w[k] for k in judged)
    if not total:
        return 0.0
    return sum(w[k] * judged[k] for k in judged) / total


# ── Job security ─────────────────────────────────────────────────────────────
# Tuned on a 30-team all-AI sim (2026-11-09) to fire about 3 or 4 GMs a
# season once the honeymoons are over (plans/owners.md, "Tuning target").
HOT_SEAT = 40
FIRE = 25
# A full +1 season adds this much; a -1 season takes up to LOSS_SCALE.
GAIN_SCALE = 15
LOSS_SCALE = 60
# Each season, before it counts, security drifts this share of the way back
# to the middle: old credit (and old blame) fades, so recent years count most.
DRIFT = 0.15
MIDDLE = 50
# Owners grade on a curve: a season's score is how far it stands from the
# league's average that year, in standard deviations times CURVE. Raw scores
# bunch near zero (most rosters do about what they should), so judged raw
# almost nobody was ever fired.
CURVE = 0.45
CURVE_MIN_TEAMS = 4
CURVE_MIN_SD = 0.05


def curved(raw: dict[str, float]) -> dict[str, float]:
    """Each team's season score on the league's curve (see CURVE). With too
    few teams to grade against, the raw scores."""
    if len(raw) < CURVE_MIN_TEAMS:
        return dict(raw)
    vals = list(raw.values())
    mean = sum(vals) / len(vals)
    sd = max(CURVE_MIN_SD, (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5)
    return {k: _clamp((v - mean) / sd * CURVE) for k, v in raw.items()}


TITLE_BONUS = 15


def grace(patience: int) -> int:
    """Where a new GM starts: about two bad seasons of room with a patient
    owner, one with an impatient one."""
    return int(round(45 + 0.35 * max(0, min(100, patience))))


def next_security(security: float, score: float, traits: dict, champion: bool) -> int:
    """Job security after a season with this score."""
    t = owners.clean_traits(traits)
    if score >= 0:
        change = score * GAIN_SCALE
    else:
        # Patience softens a bad year: 1.3x for the least patient, 0.5x for
        # the most.
        change = score * LOSS_SCALE * (1.3 - 0.8 * t["patience"] / 100)
    if champion:
        change += TITLE_BONUS
    return int(round(max(0, min(100, security + change))))


def verdict(security: int) -> str:
    """retained, warned (the hot seat) or fired, as gm_season_evaluations
    stores it."""
    if security < FIRE:
        return "fired"
    if security < HOT_SEAT:
        return "warned"
    return "retained"


# ── Firing ───────────────────────────────────────────────────────────────────
# Per archetype (plans/owners.md, "Firing parameters"). Not shown to GMs.


@dataclass(frozen=True)
class FiringRules:
    # Seasons under this owner before they can fire the GM. Security still
    # moves and the hot seat still shows during it.
    honeymoon: int = 2
    # The GM must have been on the hot seat at the last review before they
    # can be fired: a fall from safe straight past the line stops on the
    # hot seat.
    warn_first: bool = True
    # A losing season that still beats the one before has this share of its
    # loss forgiven (a rebuild that's going somewhere).
    trend_credit: float = 0.2


FIRING_RULES: dict[str, FiringRules] = {
    "The Tycoon": FiringRules(honeymoon=1, warn_first=False, trend_credit=0.0),
    "The Meddler": FiringRules(honeymoon=1, warn_first=False, trend_credit=0.0),
    "The Long-Gamer": FiringRules(honeymoon=3, trend_credit=0.6),
    "The Absentee": FiringRules(honeymoon=3),
    "The Hometown Owner": FiringRules(trend_credit=0.4),
    "The People's Owner": FiringRules(trend_credit=0.4),
}


def firing_rules(archetype: str | None) -> FiringRules:
    return FIRING_RULES.get(archetype or "", FiringRules())


@dataclass(frozen=True)
class Tenure:
    """What the owner remembers of this GM's earlier seasons under them."""

    # Seasons judged before this one.
    seasons: int = 0
    # Last season's score and job security (None: no earlier season).
    last_score: float | None = None
    last_security: int | None = None


def trended(score: float, tenure: Tenure, rules: FiringRules) -> float:
    """The season's score with the owner's credit for improving: a losing
    season better than the last loses less security."""
    if score < 0 and tenure.last_score is not None and score > tenure.last_score:
        return score * (1 - rules.trend_credit)
    return score


def judge(
    security: float,
    score: float,
    traits: dict,
    champion: bool,
    tenure: Tenure,
    rules: FiringRules,
) -> tuple[int, str, bool]:
    """Job security after the season, the verdict (retained, warned or
    fired) and whether the bare numbers alone would have fired them. The
    owner's rules can hold a firing back: during the honeymoon, or when they
    warn first and the GM wasn't on the hot seat last time. A GM held back
    sits at the bottom of the hot seat (FIRE), so an ordinary season next
    year saves them."""
    security = security + DRIFT * (MIDDLE - security)
    after = next_security(security, trended(score, tenure, rules), traits, champion)
    v = verdict(after)
    would = v == "fired"
    if would:
        in_honeymoon = tenure.seasons + 1 <= rules.honeymoon
        unwarned = rules.warn_first and (
            tenure.last_security is None or tenure.last_security >= HOT_SEAT
        )
        if in_honeymoon or unwarned:
            return FIRE, "warned", True
    return after, v, would
