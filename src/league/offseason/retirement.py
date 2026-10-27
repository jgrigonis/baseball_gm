# src/league/offseason/retirement.py
"""
Retirement chance for rostered players.

chance = age_base × playing_time_mult × form_mult × performance_mult + injury_bump

- age_base:          rises from 2% at 30 to 15% at 35, then 9 points a year.
- playing_time_mult: 1.4 for a player who never got in, 0.1 for a regular.
                     A regular (90%+ of games or starts) is also capped at 1%.
- form_mult:         grows with OVR lost from the player's recent peak and
                     with how far he sits below the league's 26-man median.
- performance_mult:  a good season (OPS or ERA better than league average)
                     cuts the chance, down to a fifth for a great one.
- injury_bump:       up to 12 points, scaled by the share of the season missed.
"""

from dataclasses import dataclass

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.stats import formulas

MIN_RETIREMENT_AGE = 30
MAX_CHANCE = 0.95

# A regular plays in this share of games (or starts) or more.
REGULAR_SHARE = 0.90
REGULAR_MAX_CHANCE = 0.01

# Relief appearances that count as a full season in a 162-game schedule.
FULL_RELIEF_APPEARANCES = 60
ROTATION_SIZE = 5

# (playing time share, multiplier), interpolated linearly.
PLAYING_TIME_MULT = [(0.0, 1.4), (0.25, 1.0), (0.5, 0.6), (0.75, 0.3), (0.9, 0.1)]

# (performance vs league, multiplier). 1.0 is league average; 1.2 is an OPS
# 20% above the league's, or an ERA that much better.
PERFORMANCE_MULT = [(1.0, 1.0), (1.1, 0.6), (1.2, 0.35), (1.3, 0.2)]
# Below this playing time a stat line is too small to count.
MIN_SHARE_FOR_PERFORMANCE = 0.25
# Below these the stat line is ignored, whatever the playing time.
MIN_PLATE_APPEARANCES = 100
MIN_PITCHING_OUTS = 60

OVR_DROP_WEIGHT = 0.10  # per OVR point below the recent peak
BELOW_MEDIAN_WEIGHT = 0.03  # per OVR point below the league's 26-man median
MAX_FORM_MULT = 2.5

INJURY_WEIGHT = 0.04
MAX_INJURY_BUMP = 0.12


@dataclass(frozen=True)
class RetirementFactors:
    """What a rostered player's retirement chance depends on, beyond age."""

    playing_time: float = 0.0  # 0..1 share of games, starts or relief work
    ovr_drop: float = 0.0  # OVR points lost from the recent peak
    below_median: float = 0.0  # OVR points below the league's 26-man median
    performance: float | None = None  # vs league average, 1.0 = average
    season_injuries: int = 0


def _interpolate(x: float, points: list[tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def age_base(age: int) -> float:
    if age < MIN_RETIREMENT_AGE:
        return 0.0
    if age < 35:
        return 0.02 + (age - 30) * 0.03
    return 0.15 + (age - 35) * 0.09


def retirement_chance(age: int, factors: RetirementFactors) -> float:
    """Chance a rostered player retires this offseason."""
    if age < MIN_RETIREMENT_AGE:
        return 0.0

    share = min(1.0, max(0.0, factors.playing_time))
    playing_time_mult = _interpolate(share, PLAYING_TIME_MULT)

    form_mult = min(
        MAX_FORM_MULT,
        (1 + OVR_DROP_WEIGHT * max(0.0, factors.ovr_drop))
        * (1 + BELOW_MEDIAN_WEIGHT * max(0.0, factors.below_median)),
    )

    performance_mult = 1.0
    if factors.performance is not None and share >= MIN_SHARE_FOR_PERFORMANCE:
        performance_mult = _interpolate(factors.performance, PERFORMANCE_MULT)

    injury_bump = min(MAX_INJURY_BUMP, factors.season_injuries * INJURY_WEIGHT) * (
        1 - share
    )

    chance = (
        age_base(age) * playing_time_mult * form_mult * performance_mult + injury_bump
    )
    if share >= REGULAR_SHARE:
        chance = min(chance, REGULAR_MAX_CHANCE)
    return min(MAX_CHANCE, chance)


def playing_time_share(stats: dict | None, season_games: int) -> float:
    """
    The best of: games played, starts out of rotation turns, and relief
    appearances out of a full reliever's workload. 0..1.
    """
    if not stats or season_games <= 0:
        return 0.0
    starts = stats.get("pitch_games_started") or 0
    relief = (stats.get("pitch_games_played") or 0) - starts
    share = max(
        (stats.get("bat_games_played") or 0) / season_games,
        starts / (season_games / ROTATION_SIZE),
        relief / (FULL_RELIEF_APPEARANCES * season_games / 162),
    )
    return min(1.0, share)


def overall_rating(skills: PlayerSkills, throws: str, is_pitcher: bool) -> float:
    """The game's own rating: best of SP/RP for pitchers, overall for hitters."""
    ratings = PlayerEvaluator.rate_player(skills, throws or "R")
    if is_pitcher:
        return max(ratings["sp"], ratings["rp"])
    return ratings["overall_player"]


def _ops(stats: dict) -> float | None:
    ab = stats.get("bat_ab") or 0
    hits = stats.get("bat_hits") or 0
    walks = stats.get("bat_walks") or 0
    hbp = stats.get("bat_hbp") or 0
    sf = stats.get("bat_sac_flys") or 0
    if ab + walks + hbp + sf == 0:
        return None
    tb = formulas.total_bases(
        hits,
        stats.get("bat_doubles") or 0,
        stats.get("bat_triples") or 0,
        stats.get("bat_home_runs") or 0,
    )
    return formulas.on_base_pct(hits, walks, hbp, ab, sf) + formulas.slugging_pct(
        tb, ab
    )


def _sum(rows: list[dict], keys: tuple[str, ...]) -> dict[str, int]:
    return {k: sum(r.get(k) or 0 for r in rows) for k in keys}


def league_baselines(
    hitters: list[dict], pitchers: list[dict]
) -> tuple[float | None, float | None]:
    """League OPS (hitters only, so pitchers batting don't drag it down) and ERA."""
    bat = _sum(
        hitters,
        (
            "bat_ab",
            "bat_hits",
            "bat_doubles",
            "bat_triples",
            "bat_home_runs",
            "bat_walks",
            "bat_hbp",
            "bat_sac_flys",
        ),
    )
    pitch = _sum(pitchers, ("pitch_outs", "pitch_earned_runs"))
    league_ops = _ops(bat)
    league_era = (
        formulas.era(pitch["pitch_earned_runs"], pitch["pitch_outs"])
        if pitch["pitch_outs"]
        else None
    )
    return league_ops, league_era


def season_performance(
    stats: dict | None,
    is_pitcher: bool,
    league_ops: float | None,
    league_era: float | None,
) -> float | None:
    """
    How good the season was against league average (1.0). OPS for hitters,
    ERA for pitchers (inverted, so higher is better). None when the stat line
    is too small to judge.
    """
    if not stats:
        return None
    if is_pitcher:
        outs = stats.get("pitch_outs") or 0
        if outs < MIN_PITCHING_OUTS or not league_era:
            return None
        era = formulas.era(stats.get("pitch_earned_runs") or 0, outs)
        return league_era / era if era > 0 else PERFORMANCE_MULT[-1][0]
    plate_appearances = sum(
        stats.get(k) or 0 for k in ("bat_ab", "bat_walks", "bat_hbp", "bat_sac_flys")
    )
    if plate_appearances < MIN_PLATE_APPEARANCES or not league_ops:
        return None
    ops = _ops(stats)
    return ops / league_ops if ops is not None else None
