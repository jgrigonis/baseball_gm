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
FIRE, at a season's end, they'd be fired (not yet: firing comes later).

Speed Blitz has no money, so profit, budget and attendance aren't judged
there; the other weights carry the score.
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
    fans_before: int | None = None
    fans_after: int | None = None
    homegrown_share: float = 0.0
    all_stars: int = 0
    award_winners: int = 0
    icons_lost: int = 0
    trades: int = 0
    rival_wins: int = 0
    rival_losses: int = 0

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
PROFIT_TARGET = 0.10
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
        margin = s.profit / s.revenue
        out["profit"] = _clamp((margin - PROFIT_TARGET) / PROFIT_SCALE)
    else:
        out["profit"] = None
    if has_money and s.budget:
        diff = (s.budget - s.payroll) / s.budget  # + under, - over
        out["budget"] = _clamp(diff * 3 if diff >= 0 else diff * 5, -1.0, 0.5)
    else:
        out["budget"] = None
    if has_money and s.fans_after is not None:
        # No ballpark to count yet: a full park is fans who care.
        out["attendance"] = _clamp((s.fans_after - 50) / 30)
        before = s.fans_before if s.fans_before is not None else 50
        out["fans"] = _clamp((s.fans_after - before) / 8)
    else:
        out["attendance"] = out["fans"] = None

    # Two years out, and the farm, against the middle of the league.
    out["future"] = _clamp((0.5 - s.rank_future) * 1.5 + (0.5 - s.farm_rank) * 0.8)
    out["homegrown"] = _clamp((s.homegrown_share - 0.3) / 0.3)
    out["stars"] = _clamp((s.all_stars + 1.5 * s.award_winners - 1.5) / 2.5)
    out["icons"] = _clamp(0.2 - 0.6 * s.icons_lost)
    out["stability"] = _clamp(0.5 - 0.25 * s.trades)
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
HOT_SEAT = 30
FIRE = 15
# A full +1 season adds this much; a -1 season takes up to LOSS_SCALE.
GAIN_SCALE = 20
LOSS_SCALE = 32
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
